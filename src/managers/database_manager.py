"""
Database manager for PostgreSQL integration.

Handles connection pooling, table creation, and data persistence for CPC+RHTP measurements.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class CPCDataAverager:
    """Handles data averaging for CPC+RHTP measurements over configurable intervals."""

    def __init__(self, dev_id: int, interval_minutes: int):
        """
        Initialize averager for a specific device.

        Args:
            dev_id: Device ID
            interval_minutes: Averaging interval in minutes (1, 5, or 60)
        """
        self.dev_id = dev_id
        self.interval_minutes = interval_minutes
        self.interval_seconds = interval_minutes * 60

        # Data buffers
        self.cpc_buffer: List[Tuple[datetime, Any]] = []  # (timestamp, CPCData)
        self.rhtp_buffer: List[Tuple[datetime, Any]] = []  # (timestamp, RHTPData)

        # Tracking
        self.interval_start: Optional[datetime] = None
        self.last_write: Optional[datetime] = None
        self.records_written: int = 0

    def add_sample(self, timestamp: datetime, cpc_data: Any, rhtp_data: Optional[Any] = None):
        """
        Add a 1Hz sample to the averaging buffer.

        Args:
            timestamp: Sample timestamp
            cpc_data: CPCData instance
            rhtp_data: RHTPData instance (optional)
        """
        if self.interval_start is None:
            self.interval_start = self._get_interval_start(timestamp)

        self.cpc_buffer.append((timestamp, cpc_data))
        if rhtp_data is not None:
            self.rhtp_buffer.append((timestamp, rhtp_data))

    def should_write(self, current_time: datetime) -> bool:
        """
        Check if current interval has elapsed and we should write averaged data.

        Args:
            current_time: Current timestamp

        Returns:
            True if interval elapsed and data should be written
        """
        if self.interval_start is None or not self.cpc_buffer:
            return False

        elapsed = (current_time - self.interval_start).total_seconds()
        return elapsed >= self.interval_seconds

    def calculate_average(self) -> Optional[Dict[str, Any]]:
        """
        Calculate averaged values from buffered samples.

        Returns:
            Dictionary with averaged values, or None if insufficient data
        """
        if not self.cpc_buffer:
            logger.warning(f"No CPC data in buffer for device {self.dev_id}")
            return None

        # Calculate interval bounds
        interval_end = self.interval_start + timedelta(seconds=self.interval_seconds)

        # Average CPC data
        cpc_values = {
            'concentration': [],
            'saturator_temperature': [],
            'condenser_temperature': [],
            'optics_temperature': [],
            'cabin_temperature': [],
            'inlet_pressure': [],
            'critical_orifice_pressure': [],
            'nozzle_pressure': [],
            'cabin_pressure': [],
            'sample_flow': [],
            'liquid_level': [],
            'pulse_duration': [],  # pulse_height in DB
            'total_errors': [],
            'status_hex': []
        }

        for _, cpc_data in self.cpc_buffer:
            for key in cpc_values.keys():
                value = getattr(cpc_data, key, None)
                if value is not None:
                    cpc_values[key].append(value)

        # Average RHTP data if available
        rhtp_values = {
            'humidity': [],
            'temperature': [],
            'pressure': []
        }

        for _, rhtp_data in self.rhtp_buffer:
            for key in rhtp_values.keys():
                value = getattr(rhtp_data, key, None)
                if value is not None:
                    rhtp_values[key].append(value)

        # Compute averages
        averaged = {
            'time': interval_end,
            'duration': f'{self.interval_minutes} minutes',
            # CPC averages
            'conc': self._mean(cpc_values['concentration']),
            'temp_sat': self._mean(cpc_values['saturator_temperature']),
            'temp_cond': self._mean(cpc_values['condenser_temperature']),
            'temp_optics': self._mean(cpc_values['optics_temperature']),
            'temp_cab': self._mean(cpc_values['cabin_temperature']),
            'pres_inl': self._mean(cpc_values['inlet_pressure']),
            'diff_pres_orf': self._mean(cpc_values['critical_orifice_pressure']),
            'diff_pres_noz': self._mean(cpc_values['nozzle_pressure']),
            'pres_amb': self._mean(cpc_values['cabin_pressure']),
            'flow_sam': self._mean(cpc_values['sample_flow']),
            'lvl_liq': self._mean(cpc_values['liquid_level']),
            'pulse_height': self._mean(cpc_values['pulse_duration']),
            # Take last error status (not averaged)
            'stat_log': cpc_values['total_errors'][-1] if cpc_values['total_errors'] else None,
            # RHTP averages (inlet conditions)
            'humidity_inlet': self._mean(rhtp_values['humidity']),  # Not in schema, but useful
            'temp_inlet': self._mean(rhtp_values['temperature']),
            'pressure_inlet': self._mean(rhtp_values['pressure'])
        }

        return averaged

    def reset_buffers(self):
        """Clear buffers and reset interval start time."""
        self.cpc_buffer.clear()
        self.rhtp_buffer.clear()
        self.interval_start = None

    def _get_interval_start(self, timestamp: datetime) -> datetime:
        """
        Calculate aligned interval start time.

        For example, if interval is 5 minutes and timestamp is 12:07:30,
        return 12:05:00.

        Args:
            timestamp: Current timestamp

        Returns:
            Aligned interval start time
        """
        # Align to interval boundaries
        minutes_since_midnight = timestamp.hour * 60 + timestamp.minute
        interval_number = minutes_since_midnight // self.interval_minutes
        aligned_minute = interval_number * self.interval_minutes

        return timestamp.replace(
            minute=aligned_minute % 60,
            hour=aligned_minute // 60,
            second=0,
            microsecond=0
        )

    @staticmethod
    def _mean(values: List[float]) -> Optional[float]:
        """Calculate mean of values, return None if empty."""
        return sum(values) / len(values) if values else None


class DatabaseManager:
    """Manages PostgreSQL connection and data persistence."""

    def __init__(self):
        """Initialize database manager."""
        self.connection_pool: Optional[pool.SimpleConnectionPool] = None
        self.connection_string: str = ""
        self.connection_string_cached: str = ""  # Cached for UI sync
        self.connected: bool = False
        self.table_name: str = "cpc_measurements"

        # Averagers for each device: {dev_id: CPCDataAverager}
        self.averagers: Dict[int, CPCDataAverager] = {}

        # Active devices using the database
        self.active_devices: set = set()

        # Error tracking
        self.last_error: Optional[str] = None
        self.connection_attempts: int = 0
        self.max_connection_attempts: int = 3

    def connect(self, connection_string: str) -> Tuple[bool, str]:
        """
        Establish connection to PostgreSQL database.

        Args:
            connection_string: PostgreSQL connection string (e.g.,
                             "postgresql://user:password@localhost:5432/dbname")

        Returns:
            Tuple of (success: bool, message: str)
        """
        self.connection_string = connection_string

        try:
            # Create connection pool (min 1, max 5 connections)
            self.connection_pool = pool.SimpleConnectionPool(
                1, 5,
                connection_string
            )

            # Test connection
            conn = self.connection_pool.getconn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
                logger.info(f"Connected to PostgreSQL: {version}")
                cursor.close()

                # Create table if not exists
                success, msg = self.create_table_if_not_exists(conn)
                if not success:
                    return False, msg

            finally:
                self.connection_pool.putconn(conn)

            self.connected = True
            self.connection_attempts = 0
            self.last_error = None
            return True, "Connected successfully"

        except psycopg2.Error as e:
            self.connected = False
            self.last_error = str(e)
            logger.error(f"Database connection failed: {e}")
            return False, f"Connection failed: {e}"
        except Exception as e:
            self.connected = False
            self.last_error = str(e)
            logger.error(f"Unexpected error during connection: {e}")
            return False, f"Unexpected error: {e}"

    def create_table_if_not_exists(self, conn=None) -> Tuple[bool, str]:
        """
        Create measurements table if it doesn't exist.

        Args:
            conn: Existing connection (optional, will get from pool if None)

        Returns:
            Tuple of (success: bool, message: str)
        """
        own_connection = conn is None
        if own_connection:
            if not self.connection_pool:
                return False, "No connection pool available"
            conn = self.connection_pool.getconn()

        try:
            cursor = conn.cursor()

            # Get current database user for ownership
            cursor.execute("SELECT current_user;")
            owner = cursor.fetchone()[0]

            # Create table based on provided schema
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS public.{self.table_name}
            (
                "time" timestamp with time zone NOT NULL,
                duration interval,
                instr_id text COLLATE pg_catalog."default",
                stat_dev text COLLATE pg_catalog."default",
                stat_enbl text COLLATE pg_catalog."default",
                flow_inl real,
                flow_aer real,
                temp_cond real,
                temp_condtr real,
                temp_sat real,
                temp_initr real,
                temp_cab real,
                diff_pres_orf real,
                flow_sam real,
                lvl_liq real,
                stat_log integer,
                nano_enh integer,
                conc real,
                pulse_height real,
                temp_optics real,
                pres_amb real,
                diff_pres_inl real,
                diff_pres_noz real,
                pres_inl real,
                current_laser real,
                counts bigint,
                mem_avbl real,
                numflag numeric(42,42),
                device_id integer,
                humidity_inlet real,
                temp_inlet real,
                pressure_inlet real,
                CONSTRAINT {self.table_name}_pkey PRIMARY KEY (time, instr_id)
            )
            TABLESPACE pg_default;
            """

            cursor.execute(create_table_sql)

            # Grant permissions
            grant_sql = f"GRANT ALL ON TABLE public.{self.table_name} TO {owner};"
            cursor.execute(grant_sql)

            conn.commit()
            cursor.close()

            logger.info(f"Table '{self.table_name}' ready")
            return True, f"Table '{self.table_name}' ready"

        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to create table: {e}")
            return False, f"Table creation failed: {e}"
        finally:
            if own_connection and conn:
                self.connection_pool.putconn(conn)

    def disconnect(self):
        """Close all database connections."""
        if self.connection_pool:
            self.connection_pool.closeall()
            self.connection_pool = None
        self.connected = False
        logger.info("Disconnected from database")

    def test_connection(self, connection_string: str) -> Tuple[bool, str]:
        """
        Test database connection without persisting it.

        Args:
            connection_string: PostgreSQL connection string

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            conn = psycopg2.connect(connection_string)
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return True, f"Connection successful: {version[:50]}..."
        except psycopg2.Error as e:
            return False, f"Connection failed: {e}"

    def create_averager(self, dev_id: int, interval_minutes: int) -> CPCDataAverager:
        """
        Create or update averager for a device.

        Args:
            dev_id: Device ID
            interval_minutes: Averaging interval (1, 5, or 60)

        Returns:
            CPCDataAverager instance
        """
        averager = CPCDataAverager(dev_id, interval_minutes)
        self.averagers[dev_id] = averager
        logger.info(f"Created averager for device {dev_id}, interval {interval_minutes} min")
        return averager

    def remove_averager(self, dev_id: int):
        """Remove averager for a device."""
        if dev_id in self.averagers:
            del self.averagers[dev_id]
            logger.info(f"Removed averager for device {dev_id}")

    def write_averaged_record(
        self,
        averaged_data: Dict[str, Any],
        device_id: int,
        serial_number: str,
        inlet_flow: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Write an averaged data record to the database.

        Args:
            averaged_data: Dictionary with averaged values from CPCDataAverager
            device_id: Device ID
            serial_number: CPC serial number (used as instr_id)
            inlet_flow: CPC inlet flow from settings

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.connected or not self.connection_pool:
            return False, "Not connected to database"

        conn = None
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()

            # Prepare insert statement
            insert_sql = f"""
            INSERT INTO public.{self.table_name} (
                time, duration, instr_id, device_id,
                flow_inl, flow_sam, temp_sat, temp_cond, temp_optics, temp_cab,
                pres_inl, diff_pres_orf, diff_pres_noz, pres_amb,
                lvl_liq, conc, pulse_height, stat_log,
                humidity_inlet, temp_inlet, pressure_inlet
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (time, instr_id) DO UPDATE SET
                conc = EXCLUDED.conc,
                temp_sat = EXCLUDED.temp_sat,
                temp_cond = EXCLUDED.temp_cond;
            """

            values = (
                averaged_data['time'],
                averaged_data['duration'],
                serial_number,
                device_id,
                inlet_flow,
                averaged_data.get('flow_sam'),
                averaged_data.get('temp_sat'),
                averaged_data.get('temp_cond'),
                averaged_data.get('temp_optics'),
                averaged_data.get('temp_cab'),
                averaged_data.get('pres_inl'),
                averaged_data.get('diff_pres_orf'),
                averaged_data.get('diff_pres_noz'),
                averaged_data.get('pres_amb'),
                averaged_data.get('lvl_liq'),
                averaged_data.get('conc'),
                averaged_data.get('pulse_height'),
                averaged_data.get('stat_log'),
                averaged_data.get('humidity_inlet'),
                averaged_data.get('temp_inlet'),
                averaged_data.get('pressure_inlet')
            )

            cursor.execute(insert_sql, values)
            conn.commit()
            cursor.close()

            logger.debug(f"Wrote averaged record for device {device_id} at {averaged_data['time']}")
            return True, "Record written successfully"

        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to write record: {e}")
            self.last_error = str(e)
            return False, f"Write failed: {e}"
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def get_latest_rows(self, limit: int = 10, device_id: Optional[int] = None) -> List[Dict]:
        """
        Retrieve latest rows from database for display in UI.

        Args:
            limit: Maximum number of rows to retrieve
            device_id: Filter by device_id (optional)

        Returns:
            List of dictionaries with row data
        """
        if not self.connected or not self.connection_pool:
            return []

        conn = None
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if device_id is not None:
                query = f"""
                SELECT time, duration, conc, temp_sat, temp_cond,
                       temp_inlet, pressure_inlet, humidity_inlet, stat_log
                FROM public.{self.table_name}
                WHERE device_id = %s
                ORDER BY time DESC
                LIMIT %s;
                """
                cursor.execute(query, (device_id, limit))
            else:
                query = f"""
                SELECT time, duration, instr_id, device_id, conc, temp_sat, temp_cond,
                       temp_inlet, pressure_inlet, humidity_inlet, stat_log
                FROM public.{self.table_name}
                ORDER BY time DESC
                LIMIT %s;
                """
                cursor.execute(query, (limit,))

            rows = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in rows]

        except psycopg2.Error as e:
            logger.error(f"Failed to retrieve rows: {e}")
            return []
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def get_record_count(self, device_id: Optional[int] = None) -> int:
        """
        Get total number of records in database.

        Args:
            device_id: Filter by device_id (optional)

        Returns:
            Record count
        """
        if not self.connected or not self.connection_pool:
            return 0

        conn = None
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()

            if device_id is not None:
                query = f"SELECT COUNT(*) FROM public.{self.table_name} WHERE device_id = %s;"
                cursor.execute(query, (device_id,))
            else:
                query = f"SELECT COUNT(*) FROM public.{self.table_name};"
                cursor.execute(query)

            count = cursor.fetchone()[0]
            cursor.close()

            return count

        except psycopg2.Error as e:
            logger.error(f"Failed to get record count: {e}")
            return 0
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def register_device(self, dev_id: int, connection_string: str) -> Tuple[bool, str]:
        """
        Register a device for database use. Connects if this is the first device.

        Args:
            dev_id: Device ID
            connection_string: PostgreSQL connection string

        Returns:
            Tuple of (success: bool, message: str)
        """
        # If this is the first device, establish connection
        if not self.active_devices and not self.connected:
            success, message = self.connect(connection_string)
            if not success:
                return False, message

        # Add device to active set
        self.active_devices.add(dev_id)
        logger.info(f"Registered device {dev_id} for database use. Active devices: {len(self.active_devices)}")

        return True, f"Device registered. {len(self.active_devices)} active device(s)."

    def unregister_device(self, dev_id: int) -> Tuple[bool, str]:
        """
        Unregister a device from database use. Disconnects if this was the last device.

        Args:
            dev_id: Device ID

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Remove device from active set
        if dev_id in self.active_devices:
            self.active_devices.remove(dev_id)
            logger.info(f"Unregistered device {dev_id} from database use. Active devices: {len(self.active_devices)}")

        # Remove averager for this device
        if dev_id in self.averagers:
            del self.averagers[dev_id]

        # If no more active devices, disconnect
        if not self.active_devices and self.connected:
            self.disconnect()
            return True, "Last device unregistered. Database disconnected."

        return True, f"Device unregistered. {len(self.active_devices)} active device(s)."

    def get_active_device_count(self) -> int:
        """
        Get number of devices currently using the database.

        Returns:
            Number of active devices
        """
        return len(self.active_devices)
