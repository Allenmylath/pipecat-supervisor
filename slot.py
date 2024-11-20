from datetime import datetime, timedelta, date
from typing import List, Tuple, Dict
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pytz

class Slot:
    # Durations in minutes
    DURATIONS = {
        'SHORT': 15,
        'MEDIUM': 30,
        'LONG': 45,
        'EXTENDED': 60
    }
    DEFAULT_DURATION = DURATIONS['MEDIUM']
    
    # Default time settings
    DEFAULT_START_TIME = "09:00"
    DEFAULT_END_TIME = "17:00"
    DEFAULT_LUNCH_START = "12:00"
    DEFAULT_LUNCH_END = "13:00"

    # Timezone settings
    TIMEZONE_LIST = {
        'IN': 'Asia/Kolkata',
        'US_EAST': 'America/New_York',
        'US_WEST': 'America/Los_Angeles',
        'UK': 'Europe/London',
        'UAE': 'Asia/Dubai',
        'SG': 'Asia/Singapore',
        'AU': 'Australia/Sydney',
        'JP': 'Asia/Tokyo',
        'CN': 'Asia/Shanghai',
        'DE': 'Europe/Berlin',
        'FR': 'Europe/Paris',
        'BR': 'America/Sao_Paulo',
        'RU': 'Europe/Moscow',
        'ZA': 'Africa/Johannesburg'
    }
    DEFAULT_TIMEZONE = TIMEZONE_LIST['IN']

    @classmethod
    def get_available_timezones(cls) -> Dict[str, str]:
        """Return list of available timezone codes and their pytz names"""
        return cls.TIMEZONE_LIST

    def __init__(self, 
                 calendar_id: str,
                 credentials_path: str,
                 slot_start_time: str = DEFAULT_START_TIME,
                 slot_end_time: str = DEFAULT_END_TIME, 
                 time_between_slots: int = 0,
                 lunch_start_time: str = DEFAULT_LUNCH_START,
                 lunch_end_time: str = DEFAULT_LUNCH_END,
                 duration: int = DEFAULT_DURATION,
                 date_value: str = None,
                 timezone_code: str = 'IN'):
        """
        Initialize Slot class
        
        Parameters:
        calendar_id: Google Calendar ID
        credentials_path: Path to Google Calendar service account credentials
        slot_start_time: Default start time for working hours (HH:MM)
        slot_end_time: Default end time for working hours (HH:MM)
        time_between_slots: Buffer time between slots in minutes
        lunch_start_time: Start time for lunch break (HH:MM)
        lunch_end_time: End time for lunch break (HH:MM)
        duration: Default duration for slots in minutes
        date_value: Default date for slots (YYYY-MM-DD)
        timezone_code: Country code for timezone (e.g., 'IN', 'US_EAST')
        """
        # Validate and set timezone
        if timezone_code not in self.TIMEZONE_LIST:
            raise ValueError(f"Invalid timezone code. Must be one of {list(self.TIMEZONE_LIST.keys())}")
        
        self.timezone = pytz.timezone(self.TIMEZONE_LIST[timezone_code])
        self.timezone_code = timezone_code
        self.calendar_id = calendar_id
        
        # Set duration
        self.duration = duration if duration in self.DURATIONS.values() else self.DEFAULT_DURATION
        
        # Initialize time parameters
        self.slot_start_time = datetime.strptime(slot_start_time, "%H:%M")
        self.slot_end_time = datetime.strptime(slot_end_time, "%H:%M")
        self.lunch_start_time = datetime.strptime(lunch_start_time, "%H:%M")
        self.lunch_end_time = datetime.strptime(lunch_end_time, "%H:%M")
        self.time_between_slots = time_between_slots

        # Initialize date
        self.date_value = self._initialize_date(date_value)
        
        # Initialize Google Calendar API
        self._initialize_google_calendar(credentials_path)

    def _initialize_date(self, date_value: str = None) -> date:
        """Initialize date with timezone-aware today if none provided"""
        if date_value is None:
            return datetime.now(self.timezone).date()
        elif isinstance(date_value, str):
            return datetime.strptime(date_value, "%Y-%m-%d").date()
        elif isinstance(date_value, date):
            return date_value
        else:
            raise ValueError("date_value must be a string 'YYYY-MM-DD' or datetime.date object")

    def _initialize_google_calendar(self, credentials_path: str):
        """Initialize Google Calendar API service"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            self.service = build('calendar', 'v3', credentials=credentials)
        except Exception as e:
            raise Exception(f"Failed to initialize Google Calendar: {str(e)}")

    def _get_datetime_string(self, date_obj: date, time_obj: datetime) -> str:
        """Convert date and time to RFC3339 timestamp"""
        combined = datetime.combine(date_obj, time_obj.time())
        localized = self.timezone.localize(combined)
        return localized.isoformat()

    def get_timezone_info(self) -> dict:
        """Return information about the current timezone"""
        now = datetime.now(self.timezone)
        return {
            'code': self.timezone_code,
            'name': self.TIMEZONE_LIST[self.timezone_code],
            'current_time': now.strftime('%H:%M'),
            'current_date': now.strftime('%Y-%m-%d'),
            'utc_offset': now.strftime('%z')
        }

    def convert_time_to_timezone(self, time_str: str, from_timezone_code: str) -> str:
        """Convert time from one timezone to the current timezone"""
        if from_timezone_code not in self.TIMEZONE_LIST:
            raise ValueError(f"Invalid timezone code. Must be one of {list(self.TIMEZONE_LIST.keys())}")
            
        from_tz = pytz.timezone(self.TIMEZONE_LIST[from_timezone_code])
        time_obj = datetime.strptime(time_str, "%H:%M")
        today = datetime.now(from_tz).date()
        dt = datetime.combine(today, time_obj.time())
        dt_with_tz = from_tz.localize(dt)
        
        converted = dt_with_tz.astimezone(self.timezone)
        return converted.strftime("%H:%M")

    def get_existing_events(self, date_str: str = None) -> List[dict]:
        """Get existing events from Google Calendar for a specific date"""
        try:
            check_date = datetime.strptime(date_str or self.date_value.strftime("%Y-%m-%d"), "%Y-%m-%d").date()
            start_datetime = self._get_datetime_string(check_date, self.slot_start_time)
            end_datetime = self._get_datetime_string(check_date, self.slot_end_time)

            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_datetime,
                timeMax=end_datetime,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            return events_result.get('items', [])
        except Exception as e:
            raise Exception(f"Failed to fetch calendar events: {str(e)}")

    def is_slot_available(self, start_time: str = None, duration: int = None, check_date: str = None) -> bool:
        """Check if a specific time slot is available"""
        try:
            start_time = start_time or self.slot_start_time.strftime("%H:%M")
            duration = duration or self.duration
            date_str = check_date or self.date_value.strftime("%Y-%m-%d")
            
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_obj = datetime.strptime(start_time, "%H:%M")
            end_obj = start_obj + timedelta(minutes=duration)

            start_datetime = self._get_datetime_string(date_obj, start_obj)
            end_datetime = self._get_datetime_string(date_obj, end_obj)

            events = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_datetime,
                timeMax=end_datetime,
                singleEvents=True
            ).execute()

            return len(events.get('items', [])) == 0
        except Exception as e:
            raise Exception(f"Failed to check slot availability: {str(e)}")

    def is_valid_time(self, start_time: str = None, duration: int = None, check_date: str = None) -> Tuple[bool, str]:
        """Check if the requested time is valid"""
        try:
            start_time = start_time or self.slot_start_time.strftime("%H:%M")
            duration = duration or self.duration
            check_date = check_date or self.date_value.strftime("%Y-%m-%d")
            
            date_obj = datetime.strptime(check_date, "%Y-%m-%d").date()
            
            # Validate date is not in the past
            if date_obj < date.today():
                return False, "Cannot book slots in the past"

            # Validate duration
            if duration not in self.DURATIONS.values():
                return False, f"Invalid duration. Must be one of {list(self.DURATIONS.values())} minutes"

            # Convert requested time to datetime
            req_time = datetime.strptime(start_time, "%H:%M")
            
            # Check if start time is within working hours
            if req_time < self.slot_start_time or req_time >= self.slot_end_time:
                return False, "Start time is outside working hours"
            
            # Calculate end time
            end_time = req_time + timedelta(minutes=duration)
            
            # Check if end time exceeds working hours
            if end_time > self.slot_end_time:
                return False, "Slot would exceed working hours"
            
            # Check if slot overlaps with lunch
            if not (end_time <= self.lunch_start_time or req_time >= self.lunch_end_time):
                return False, "Slot overlaps with lunch break"
            
            # Check if time aligns with 15-minute intervals
            minutes_from_start = (req_time - self.slot_start_time).total_seconds() / 60
            if minutes_from_start % 15 != 0:
                return False, "Invalid start time. Slots must start at 15-minute intervals"
            
            return True, "Valid slot time"
            
        except ValueError as e:
            return False, str(e)

    def get_available_slots(self, duration: int = None, requested_date: str = None) -> List[dict]:
        """Return list of available slots"""
        duration = duration or self.duration
        if duration not in self.DURATIONS.values():
            raise ValueError(f"Invalid duration. Must be one of {list(self.DURATIONS.values())} minutes")

        check_date = requested_date or self.date_value.strftime("%Y-%m-%d")
        available_slots = []
        current_time = self.slot_start_time

        while current_time < self.slot_end_time:
            time_str = current_time.strftime("%H:%M")
            
            is_valid, _ = self.is_valid_time(time_str, duration, check_date)
            
            if is_valid and self.is_slot_available(time_str, duration, check_date):
                slot_info = {
                    "date": check_date,
                    "start_time": time_str,
                    "end_time": self.get_end_time(time_str),
                    "duration": self.duration
                }
                available_slots.append(slot_info)
            
            current_time += timedelta(minutes=15)

        return available_slots

    def get_end_time(self, start_time: str = None) -> str:
        """Calculate the end time for a slot using default duration"""
        start_time = start_time or self.slot_start_time.strftime("%H:%M")
        start = datetime.strptime(start_time, "%H:%M")
        end = start + timedelta(minutes=self.duration)
        return end.strftime("%H:%M")

    def get_date_string(self) -> str:
        """Return the current date value as a formatted string"""
        return self.date_value.strftime("%Y-%m-%d")
