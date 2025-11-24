"""
Tests for file parser module.
"""

import unittest
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from managers.file_parser import CPCFileParser, RHTPFileParser, TimestampMerger


class TestCPCFileParser(unittest.TestCase):
    """Tests for CPCFileParser class."""

    def setUp(self):
        """Set up test fixtures."""
        self.parser = CPCFileParser()

    def test_extract_serial_from_filename(self):
        """Test serial number extraction from filename."""
        # Valid filename
        filepath = "/path/to/20250817_000000_2491701211_CPC.dat"
        serial = self.parser.extract_serial_from_filename(filepath)
        self.assertEqual(serial, "2491701211")

        # Another valid filename
        filepath2 = "20250101_120000_1234567890_CPC.par"
        serial2 = self.parser.extract_serial_from_filename(filepath2)
        self.assertEqual(serial2, "1234567890")

        # Invalid filename
        filepath3 = "invalid_filename.dat"
        serial3 = self.parser.extract_serial_from_filename(filepath3)
        self.assertIsNone(serial3)

    def test_parse_dat_file(self):
        """Test parsing of CPC .dat file."""
        # Create temporary test file
        test_data = """YYYY.MM.DD hh:mm:ss,Concentration (#/cc),Dead time (µs),Number of pulses,Saturator T (C),Condenser T (C),Optics T (C),Cabin T (C),Inlet P (kPa),Critical orifice P (kPa),Nozzle P (kPa),Cabin P (kPa),Liquid level,Pulse ratio,Total CPC errors,System status error
2025.08.17 00:00:00,1380.701172,399.0,2288.0,35.0,28.0,36.0,27.77,100.0,37.0,2.4,nan,1,nan,0,0x0000
2025.08.17 00:00:01,1427.045044,408.0,2364.0,35.0,28.0,36.0,27.76,99.9,37.1,2.4,nan,1,nan,0,0x0000
2025.08.17 00:00:02,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
2025.08.17 00:00:03,1331.782227,377.0,2208.0,35.0,28.0,36.0,27.76,100.0,37.1,2.4,nan,1,nan,0,0x0000
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='_2491701211_CPC.dat', delete=False) as f:
            f.write(test_data)
            temp_path = f.name

        try:
            records, serial = self.parser.parse_dat_file(temp_path)

            # Check serial number
            self.assertEqual(serial, "2491701211")

            # Should have 3 valid records (skipped all-nan row)
            self.assertEqual(len(records), 3)

            # Check first record
            first = records[0]
            self.assertEqual(first['timestamp'], datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc))
            self.assertAlmostEqual(first['concentration'], 1380.701172)
            self.assertAlmostEqual(first['temp_saturator'], 35.0)
            self.assertEqual(first['status_error'], '0x0000')
            self.assertIsNone(first['pressure_cabin'])  # Was nan in data

        finally:
            os.unlink(temp_path)

    def test_parse_par_file(self):
        """Test parsing of CPC .par file."""
        test_data = """YYYY.MM.DD hh:mm:ss,Averaging time (s),Nominal flow rate (lpm),Flow rate (lpm),Saturator T setpoint (C),Condenser T setpoint (C),Optics T setpoint (C),Autofill,OPC counter threshold voltage (mV),OPC counter threshold 2 voltage (mV),Water removal,Dead time correction,Drain,K-factor,Tau,Command input
2025.08.17 00:00:00,0.1,1.07,1.07,35.0,28.0,36.0,1,150.0,nan,0,1.0,0,1.06,318.22
2025.08.17 01:00:00,0.1,1.07,1.08,35.0,28.0,36.0,1,150.0,nan,0,1.0,0,1.06,318.22
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='_CPC.par', delete=False) as f:
            f.write(test_data)
            temp_path = f.name

        try:
            flow_map = self.parser.parse_par_file(temp_path)

            # Should have 2 entries
            self.assertEqual(len(flow_map), 2)

            # Check values
            ts1 = datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc)
            ts2 = datetime(2025, 8, 17, 1, 0, 0, tzinfo=timezone.utc)

            self.assertAlmostEqual(flow_map[ts1], 1.07)
            self.assertAlmostEqual(flow_map[ts2], 1.08)

        finally:
            os.unlink(temp_path)

    def test_merge_dat_par(self):
        """Test merging .dat and .par data."""
        # Create sample dat records
        dat_records = [
            {'timestamp': datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc), 'concentration': 1000},
            {'timestamp': datetime(2025, 8, 17, 0, 0, 30, tzinfo=timezone.utc), 'concentration': 1100},
            {'timestamp': datetime(2025, 8, 17, 1, 0, 0, tzinfo=timezone.utc), 'concentration': 1200},
            {'timestamp': datetime(2025, 8, 17, 1, 0, 30, tzinfo=timezone.utc), 'concentration': 1300},
        ]

        # Create sample par flow map
        par_flow_map = {
            datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc): 1.07,
            datetime(2025, 8, 17, 1, 0, 0, tzinfo=timezone.utc): 1.08,
        }

        merged = self.parser.merge_dat_par(dat_records, par_flow_map)

        # Check flow rates were assigned correctly
        self.assertAlmostEqual(merged[0]['flow_rate'], 1.07)
        self.assertAlmostEqual(merged[1]['flow_rate'], 1.07)  # Uses first flow
        self.assertAlmostEqual(merged[2]['flow_rate'], 1.08)  # Uses second flow
        self.assertAlmostEqual(merged[3]['flow_rate'], 1.08)

    def test_merge_dat_par_no_par(self):
        """Test merging when no .par file provided."""
        dat_records = [
            {'timestamp': datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc), 'concentration': 1000},
        ]

        merged = self.parser.merge_dat_par(dat_records, {})

        # Flow rate should be None
        self.assertIsNone(merged[0]['flow_rate'])


class TestRHTPFileParser(unittest.TestCase):
    """Tests for RHTPFileParser class."""

    def setUp(self):
        """Set up test fixtures."""
        self.parser = RHTPFileParser()

    def test_parse_dat_file(self):
        """Test parsing of RHTP .dat file."""
        test_data = """YYYY.MM.DD hh:mm:ss,RH (%),T (C),P (Pa)
2025.08.17 00:00:00,45.2,22.5,101300
2025.08.17 00:00:01,45.3,22.6,101350
2025.08.17 00:00:02,nan,nan,nan
2025.08.17 00:00:03,45.1,22.4,101280
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='_RHTP.dat', delete=False) as f:
            f.write(test_data)
            temp_path = f.name

        try:
            records = self.parser.parse_dat_file(temp_path)

            # Should have 3 valid records (skipped all-nan row)
            self.assertEqual(len(records), 3)

            # Check first record
            first = records[0]
            self.assertEqual(first['timestamp'], datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc))
            self.assertAlmostEqual(first['humidity'], 45.2)
            self.assertAlmostEqual(first['temperature'], 22.5)
            # Pressure should be converted from Pa to hPa
            self.assertAlmostEqual(first['pressure'], 1013.0)

            # Check second record
            second = records[1]
            self.assertAlmostEqual(second['pressure'], 1013.5)

        finally:
            os.unlink(temp_path)


class TestTimestampMerger(unittest.TestCase):
    """Tests for TimestampMerger class."""

    def test_merge_cpc_rhtp_exact_match(self):
        """Test merging with exact timestamp matches."""
        cpc_records = [
            {'timestamp': datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc), 'concentration': 1000},
            {'timestamp': datetime(2025, 8, 17, 0, 0, 1, tzinfo=timezone.utc), 'concentration': 1100},
        ]

        rhtp_records = [
            {'timestamp': datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc), 'humidity': 45.0, 'temperature': 22.0, 'pressure': 1013.0},
            {'timestamp': datetime(2025, 8, 17, 0, 0, 1, tzinfo=timezone.utc), 'humidity': 45.1, 'temperature': 22.1, 'pressure': 1013.1},
        ]

        merged = TimestampMerger.merge_cpc_rhtp(cpc_records, rhtp_records)

        # Check first record
        self.assertAlmostEqual(merged[0]['humidity_inlet'], 45.0)
        self.assertAlmostEqual(merged[0]['temp_inlet'], 22.0)
        self.assertAlmostEqual(merged[0]['pressure_inlet'], 1013.0)

        # Check second record
        self.assertAlmostEqual(merged[1]['humidity_inlet'], 45.1)

    def test_merge_cpc_rhtp_no_rhtp(self):
        """Test merging when no RHTP data provided."""
        cpc_records = [
            {'timestamp': datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc), 'concentration': 1000},
        ]

        merged = TimestampMerger.merge_cpc_rhtp(cpc_records, [])

        # RHTP fields should be None
        self.assertIsNone(merged[0]['humidity_inlet'])
        self.assertIsNone(merged[0]['temp_inlet'])
        self.assertIsNone(merged[0]['pressure_inlet'])

    def test_merge_cpc_rhtp_tolerance(self):
        """Test merging with timestamp tolerance."""
        from datetime import timedelta

        cpc_records = [
            {'timestamp': datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc), 'concentration': 1000},
            {'timestamp': datetime(2025, 8, 17, 0, 0, 2, tzinfo=timezone.utc), 'concentration': 1100},
        ]

        # RHTP timestamp slightly offset
        rhtp_records = [
            {'timestamp': datetime(2025, 8, 17, 0, 0, 0, tzinfo=timezone.utc) + timedelta(milliseconds=500),
             'humidity': 45.0, 'temperature': 22.0, 'pressure': 1013.0},
        ]

        merged = TimestampMerger.merge_cpc_rhtp(cpc_records, rhtp_records, tolerance_seconds=1.0)

        # First CPC record should match RHTP (within 1 second)
        self.assertAlmostEqual(merged[0]['humidity_inlet'], 45.0)

        # Second CPC record should not match (more than 1 second away)
        self.assertIsNone(merged[1]['humidity_inlet'])


if __name__ == '__main__':
    unittest.main()
