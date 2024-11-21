from datetime import datetime, time, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import List, Optional

class Slot:
    def __init__(self, 
                 datetime_obj: datetime,
                 business_start: time = time(9, 0),    # 9 AM default
                 business_end: time = time(17, 0),     # 5 PM default
                 duration: int = 30,                   # 30 minutes default
                 calendar_id: str = 'johananddijo@gmail.com'):  # Updated default calendar
        """
        Initialize a slot with configurable parameters.
        
        Args:
            datetime_obj: The datetime for the slot
            business_start: Daily business start time (default: 9 AM)
            business_end: Daily business end time (default: 5 PM)
            duration: Slot duration in minutes (default: 30)
            calendar_id: Google Calendar ID (default: 'johananddijo@gmail.com')
        """
        self.datetime = datetime_obj
        self.business_start = business_start
        self.business_end = business_end
        self.duration = duration
        self.calendar_id = calendar_id
        self.lunch_start = time(13, 0)  # 1 PM
        self.lunch_end = time(14, 0)    # 2 PM
        self._setup_calendar()
        
    def _setup_calendar(self):
        """
        Set up Google Calendar service using credentials from a JSON file.
    
        The JSON file should be a Google Cloud service account key file.
        Ensure the service account has the necessary Calendar API permissions.
        """
        SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    # Load credentials from the JSON file
        self.credentials = service_account.Credentials.from_service_account_file(
            filename='/content/supple-framing-430709-i1-08e095a2194e.json',  # Replace with your JSON file path
            scopes=SCOPES
        )
        self.service = build('calendar', 'v3', credentials=self.credentials)

    def _overlaps_with_lunch(self) -> bool:
        """Check if the slot overlaps with lunch time."""
        slot_start_time = self.datetime.time()
        slot_end_time = (self.datetime + timedelta(minutes=self.duration)).time()
        
        # Check if slot starts during lunch
        starts_during_lunch = self.lunch_start <= slot_start_time < self.lunch_end
        
        # Check if slot ends during lunch
        ends_during_lunch = self.lunch_start < slot_end_time <= self.lunch_end
        
        # Check if slot encompasses entire lunch period
        encompasses_lunch = slot_start_time <= self.lunch_start and slot_end_time >= self.lunch_end
        
        return starts_during_lunch or ends_during_lunch or encompasses_lunch

    def is_available(self) -> bool:
        """Check if the slot is available in Google Calendar."""
        start_time = self.datetime
        end_time = self.datetime + timedelta(minutes=self.duration)
        
        events_result = self.service.events().list(
            calendarId=self.calendar_id,
            timeMin=start_time.isoformat() + 'Z',
            timeMax=end_time.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return len(events_result.get('items', [])) == 0
    
    def is_valid(self) -> bool:
        """
        Check if slot time is valid (during business hours, not in past, 
        and not during lunch time).
        """
        current_time = datetime.now()
        business_start = datetime.combine(self.datetime.date(), self.business_start)
        business_end = datetime.combine(self.datetime.date(), self.business_end)
        
        return (
            self.datetime > current_time and
            business_start <= self.datetime <= business_end and
            self.datetime.weekday() < 5 and  # Monday = 0, Friday = 4
            not self._overlaps_with_lunch()  # Check for lunch time overlap
        )

    @classmethod
    def get_available_slots(cls, 
                          date: datetime.date,
                          business_start: time = time(9, 0),
                          business_end: time = time(17, 0),
                          duration: int = 30,
                          calendar_id: str = 'johananddijo@gmail.com') -> List['Slot']:
        """
        Get all available slots for a given date.
        
        Args:
            date: The date to check for available slots
            business_start: Daily business start time (default: 9 AM)
            business_end: Daily business end time (default: 5 PM)
            duration: Slot duration in minutes (default: 30)
            calendar_id: Google Calendar ID (default: 'johananddijo@gmail.com')
            
        Returns:
            List of available Slot objects
        """
        available_slots = []
        current_time = datetime.combine(date, business_start)
        end_time = datetime.combine(date, business_end)
        
        while current_time < end_time:
            test_slot = cls(
                datetime_obj=current_time,
                business_start=business_start,
                business_end=business_end,
                duration=duration,
                calendar_id=calendar_id
            )
            if test_slot.is_valid() and test_slot.is_available():
                available_slots.append(test_slot)
            current_time += timedelta(minutes=duration)
            
        return available_slots
