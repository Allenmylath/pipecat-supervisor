from datetime import datetime, time, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import List, Optional, Tuple
import pytz

IST = pytz.timezone('Asia/Kolkata')

class Slot:
    def __init__(self,
                 datetime_obj: datetime,
                 business_start: time = time(9, 0),    # 9 AM default
                 business_end: time = time(17, 0),     # 5 PM default
                 duration: int = 30,                   # 30 minutes default
                 calendar_id: str = 'johananddijo@gmail.com'):  # Default calendar
        """
        Initialize a slot with configurable parameters.
        """
        # Handle timezone conversion properly
        if datetime_obj.tzinfo is None:
            self.datetime = IST.localize(datetime_obj)
        else:
            self.datetime = datetime_obj.astimezone(IST)
            
        self.business_start = business_start
        self.business_end = business_end
        self.duration = duration
        self.calendar_id = calendar_id
        self.lunch_start = time(13, 0)  # 1 PM
        self.lunch_end = time(14, 0)    # 2 PM
        self._setup_calendar()

    def _setup_calendar(self):
        """Set up Google Calendar service."""
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        self.credentials = service_account.Credentials.from_service_account_file(
            filename='/content/supple-framing-430709-i1-08e095a2194e.json',
            scopes=SCOPES
        )
        self.service = build('calendar', 'v3', credentials=self.credentials)

    def _overlaps_with_lunch(self) -> bool:
        """Check if the slot overlaps with lunch time."""
        # Get start and end datetime objects for the slot
        slot_start = self.datetime
        slot_end = self.datetime + timedelta(minutes=self.duration)
        
        # Create datetime objects for lunch period on the same day
        lunch_start = datetime.combine(self.datetime.date(), self.lunch_start)
        lunch_end = datetime.combine(self.datetime.date(), self.lunch_end)
        
        # Localize lunch times to IST
        lunch_start = IST.localize(lunch_start)
        lunch_end = IST.localize(lunch_end)
        
        # Check for overlap
        return (
            (slot_start < lunch_end) and 
            (slot_end > lunch_start)
        )

    def _overlaps_with_event(self, event_start: datetime, event_end: datetime) -> bool:
        """Check if the slot overlaps with a given event."""
        slot_start = self.datetime
        slot_end = self.datetime + timedelta(minutes=self.duration)
        
        return (slot_start < event_end) and (slot_end > event_start)

    def is_valid(self) -> Tuple[bool, List[str]]:
        """Check if slot time is valid and return reasons for invalidity if any."""
        reasons = []
        current_time = datetime.now(IST)
        business_start = datetime.combine(self.datetime.date(), self.business_start)
        business_end = datetime.combine(self.datetime.date(), self.business_end)
        
        # Localize business hours
        business_start = IST.localize(business_start)
        business_end = IST.localize(business_end)

        # Check if slot is in the past
        if self.datetime <= current_time:
            reasons.append("Slot is in the past")

        # Check if slot is within business hours
        if self.datetime < business_start:
            reasons.append(f"Slot starts before business hours (before {self.business_start.strftime('%I:%M %p')})")
        if self.datetime >= business_end:
            reasons.append(f"Slot starts after business hours (after {self.business_end.strftime('%I:%M %p')})")

        # Check if slot is on a weekend
        if self.datetime.weekday() >= 5:
            reasons.append("Slot is on a weekend")

        # Check if slot overlaps with lunch time
        if self._overlaps_with_lunch():
            reasons.append(f"Slot overlaps with lunch time ({self.lunch_start.strftime('%I:%M %p')} - {self.lunch_end.strftime('%I:%M %p')})")

        return (len(reasons) == 0, reasons)

    @classmethod
    def get_available_slots(cls,
                          date: datetime.date,
                          business_start: time = time(9, 0),
                          business_end: time = time(17, 0),
                          duration: int = 30,
                          calendar_id: str = 'johananddijo@gmail.com') -> List['Slot']:
        """Get all available slots for a given date using a single API call."""
        # Create a temporary slot object to access the calendar service
        temp_slot = cls(
            datetime_obj=datetime.combine(date, business_start),
            business_start=business_start,
            business_end=business_end,
            duration=duration,
            calendar_id=calendar_id
        )
        
        # Define the time boundaries for the day
        day_start = datetime.combine(date, business_start)
        day_end = datetime.combine(date, business_end)
        
        # Localize the times
        day_start = IST.localize(day_start)
        day_end = IST.localize(day_end)
        
        # Fetch all events for the day in a single API call
        events_result = temp_slot.service.events().list(
            calendarId=calendar_id,
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        # Process events into a list of busy periods
        busy_periods = []
        for event in events_result.get('items', []):
            start = event['start'].get('dateTime')
            end = event['end'].get('dateTime')
            if start and end:
                start_dt = datetime.fromisoformat(start).astimezone(IST)
                end_dt = datetime.fromisoformat(end).astimezone(IST)
                busy_periods.append((start_dt, end_dt))
        
        # Generate all possible slots
        available_slots = []
        current_time = day_start
        
        while current_time < day_end:
            test_slot = cls(
                datetime_obj=current_time,
                business_start=business_start,
                business_end=business_end,
                duration=duration,
                calendar_id=calendar_id
            )
            
            # Check if slot is valid (business hours, weekends, lunch time)
            is_valid, reasons = test_slot.is_valid()
            
            if is_valid:
                # Check if slot overlaps with any busy periods
                is_available = True
                for busy_start, busy_end in busy_periods:
                    if test_slot._overlaps_with_event(busy_start, busy_end):
                        is_available = False
                        break
                        
                if is_available:
                    available_slots.append(test_slot)
            
            current_time += timedelta(minutes=duration)
        
        return available_slots
