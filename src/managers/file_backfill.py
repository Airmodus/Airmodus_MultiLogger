"""
File backfill orchestration manager.

This module orchestrates the process of parsing historical data files,
averaging them, and writing to the ACTRIS database.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from PyQt5.QtCore import QObject, pyqtSignal

from .file_parser import CPCFileParser, RHTPFileParser, TimestampMerger
from .database_manager import CPCDataAverager


class FileBackfillManager(QObject):
    """
    Manages the backfill process from historical files to database.

    Signals:
        progress: Emits (current, total, message) for UI updates
        finished: Emits (success, statistics) when complete
    """

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(bool, dict)  # success, statistics

    def __init__(self, database_manager):
        super().__init__()
        self.database_manager = database_manager
        self.cpc_parser = CPCFileParser()
        self.rhtp_parser = RHTPFileParser()
        self.merger = TimestampMerger()

    def backfill_from_files(self,
                           cpc_dat_path: str,
                           cpc_par_path: Optional[str],
                           rhtp_dat_path: Optional[str],
                           averaging_interval_minutes: int,
                           overwrite_existing: bool = False) -> Tuple[bool, Dict]:
        """
        Execute the complete backfill process.

        Steps:
        1. Parse CPC .dat file
        2. Parse CPC .par file (if provided)
        3. Merge CPC dat + par
        4. Parse RHTP .dat file (if provided)
        5. Merge CPC + RHTP by timestamp
        6. Apply time averaging
        7. Write to database

        Args:
            cpc_dat_path: Path to CPC .dat file (required)
            cpc_par_path: Path to CPC .par file (optional)
            rhtp_dat_path: Path to RHTP .dat file (optional)
            averaging_interval_minutes: Time interval for averaging (1, 5, 10, 15, 60, 180)
            overwrite_existing: If True, update existing records; if False, skip duplicates

        Returns:
            Tuple of (success: bool, statistics: dict)
        """
        try:
            statistics = {
                'cpc_records_parsed': 0,
                'rhtp_records_parsed': 0,
                'merged_records': 0,
                'averaged_records': 0,
                'records_written': 0,
                'records_skipped': 0,
                'errors': 0,
                'serial_number': None,
                'date_range': None
            }

            # Step 1: Parse CPC .dat file
            self.progress.emit(0, 7, "Parsing CPC .dat file...")
            cpc_records, serial_number = self.cpc_parser.parse_dat_file(cpc_dat_path)
            statistics['cpc_records_parsed'] = len(cpc_records)
            statistics['serial_number'] = serial_number

            if not cpc_records:
                return False, {'error': 'No valid CPC data found in .dat file'}

            # Get date range
            first_ts = cpc_records[0]['timestamp']
            last_ts = cpc_records[-1]['timestamp']
            statistics['date_range'] = (first_ts, last_ts)

            # Step 2: Parse CPC .par file (optional)
            self.progress.emit(1, 7, "Parsing CPC .par file...")
            par_flow_map = {}
            if cpc_par_path:
                par_flow_map = self.cpc_parser.parse_par_file(cpc_par_path)

            # Step 3: Merge CPC dat + par
            self.progress.emit(2, 7, "Merging CPC measurements with flow settings...")
            cpc_records = self.cpc_parser.merge_dat_par(cpc_records, par_flow_map)
            statistics['merged_records'] = len(cpc_records)

            # Step 4: Parse RHTP .dat file (optional)
            self.progress.emit(3, 7, "Parsing RHTP .dat file...")
            rhtp_records = []
            if rhtp_dat_path:
                rhtp_records = self.rhtp_parser.parse_dat_file(rhtp_dat_path)
                statistics['rhtp_records_parsed'] = len(rhtp_records)

            # Step 5: Merge CPC + RHTP
            self.progress.emit(4, 7, "Merging CPC and RHTP data by timestamp...")
            merged_records = self.merger.merge_cpc_rhtp(cpc_records, rhtp_records)

            # Step 6: Apply time averaging
            self.progress.emit(5, 7, f"Averaging data to {averaging_interval_minutes}-minute intervals...")
            averaged_records = self._average_records(merged_records, averaging_interval_minutes, serial_number)
            statistics['averaged_records'] = len(averaged_records)

            # Step 7: Write to database
            self.progress.emit(6, 7, "Writing to database...")
            write_stats = self._write_to_database(averaged_records, overwrite_existing)
            statistics['records_written'] = write_stats['written']
            statistics['records_skipped'] = write_stats['skipped']
            statistics['errors'] = write_stats['errors']

            self.progress.emit(7, 7, "Backfill complete!")
            return True, statistics

        except Exception as e:
            error_msg = f"Backfill failed: {str(e)}"
            return False, {'error': error_msg}

    def _average_records(self, records: List[Dict], interval_minutes: int, serial_number: str) -> List[Dict]:
        """
        Apply time-averaging to 1Hz records.

        Groups records by time interval and calculates averages.

        Args:
            records: List of 1Hz measurement records
            interval_minutes: Averaging interval in minutes
            serial_number: CPC serial number

        Returns:
            List of averaged records ready for database insertion
        """
        if not records:
            return []

        # Create time bins
        interval_delta = timedelta(minutes=interval_minutes)
        first_timestamp = records[0]['timestamp']

        # Round down to nearest interval
        start_time = first_timestamp.replace(second=0, microsecond=0)
        minute = start_time.minute
        minute = (minute // interval_minutes) * interval_minutes
        start_time = start_time.replace(minute=minute)

        # Group records by time bin
        bins = {}
        for record in records:
            # Calculate which bin this record belongs to
            elapsed = record['timestamp'] - start_time
            bin_index = int(elapsed.total_seconds() // (interval_minutes * 60))
            bin_start = start_time + timedelta(minutes=bin_index * interval_minutes)

            if bin_start not in bins:
                bins[bin_start] = []
            bins[bin_start].append(record)

        # Calculate averages for each bin
        averaged_records = []
        for bin_start, bin_records in sorted(bins.items()):
            if not bin_records:
                continue

            bin_end = bin_start + interval_delta

            # Calculate averages (skip None values)
            def avg(field_name):
                values = [r[field_name] for r in bin_records if r.get(field_name) is not None]
                return sum(values) / len(values) if values else None

            # Use last non-None value for status fields
            def last(field_name):
                for r in reversed(bin_records):
                    if r.get(field_name) is not None:
                        return r[field_name]
                return None

            averaged = {
                'starttime': bin_start,
                'time': bin_end,
                'duration': f'{interval_minutes} minutes',
                'instr_id': serial_number,
                'device_id': None,  # Will be set by database if CPC device exists
                'conc': avg('concentration'),
                'flow_inl': avg('flow_rate'),
                'temp_sat': avg('temp_saturator'),
                'temp_cond': avg('temp_condenser'),
                'temp_optics': avg('temp_optics'),
                'temp_cab': avg('temp_cabin'),
                'pres_inl': avg('pressure_inlet'),
                'diff_pres_orf': avg('pressure_critical_orifice'),
                'diff_pres_noz': avg('pressure_nozzle'),
                'pres_amb': avg('pressure_cabin'),
                'lvl_liq': avg('liquid_level'),
                'pulse_height': None,  # Not in .dat file
                'current_laser': None,  # Not in .dat file
                'stat_log': last('total_errors'),
                'status_hex': last('status_error'),
                'humidity_inlet': avg('humidity_inlet'),
                'temp_inlet': avg('temp_inlet'),
                'pressure_inlet': avg('pressure_inlet')
            }

            averaged_records.append(averaged)

        return averaged_records

    def _write_to_database(self, averaged_records: List[Dict], overwrite: bool) -> Dict:
        """
        Write averaged records to database.

        Args:
            averaged_records: List of averaged records
            overwrite: If True, update existing records; if False, skip

        Returns:
            Dict with 'written', 'skipped', 'errors' counts, 'error_messages' list
        """
        stats = {'written': 0, 'skipped': 0, 'errors': 0, 'error_messages': []}

        if not self.database_manager.connected:
            stats['errors'] = len(averaged_records)
            stats['error_messages'].append('Database not connected')
            return stats

        # Write in batches for better performance
        batch_size = 1000
        for i in range(0, len(averaged_records), batch_size):
            batch = averaged_records[i:i+batch_size]

            for record in batch:
                try:
                    # Extract parameters from record
                    device_id = record.get('device_id')
                    serial_number = record.get('instr_id')
                    inlet_flow = record.get('flow_inl')

                    success, message = self.database_manager.write_averaged_record(
                        record, device_id, serial_number, inlet_flow
                    )

                    if success:
                        stats['written'] += 1
                    else:
                        # Always count as error and capture message
                        stats['errors'] += 1
                        # Store first 10 unique error messages
                        if message and len(stats['error_messages']) < 10:
                            if message not in stats['error_messages']:
                                stats['error_messages'].append(message)

                        # Check if it's a duplicate conflict (for stats only)
                        if 'duplicate' in message.lower() or 'conflict' in message.lower():
                            if overwrite:
                                # Note: Should have been handled by ON CONFLICT DO UPDATE
                                pass
                            else:
                                stats['skipped'] += 1
                                stats['errors'] -= 1  # Don't count skips as errors

                except Exception as e:
                    stats['errors'] += 1
                    error_msg = f"Exception: {str(e)}"
                    if len(stats['error_messages']) < 10 and error_msg not in stats['error_messages']:
                        stats['error_messages'].append(error_msg)

            # Emit progress update for this batch
            progress = min(i + batch_size, len(averaged_records))
            self.progress.emit(progress, len(averaged_records),
                             f"Writing to database: {progress}/{len(averaged_records)}")

        return stats
