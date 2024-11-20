from datetime import datetime, timedelta
from typing import List, Dict
from slot import Slot

class Date(Slot):
    # Define weekend days (0 = Monday, 6 = Sunday in Python's datetime)
    WEEKEND_DAYS = {5, 6}  # Saturday and Sunday
    
    def __init__(self, 
                 calendar_id: str,
                 credentials_path: str,
                 slot_start_time: str = Slot.DEFAULT_START_TIME,
                 slot_end_time: str = Slot.DEFAULT_END_TIME,
                 time_between_slots: int = 0,
                 lunch_start_time: str = Slot.DEFAULT_LUNCH_START,
                 lunch_end_time: str = Slot.DEFAULT_LUNCH_END,
                 duration: int = Slot.DEFAULT_DURATION,
                 date_value: str = None,
                 timezone_code: str = 'IN',
                 holidays: List[str] = None):
        """
        Initialize Date class
        
        Parameters:
        All parameters from Slot class, plus:
        holidays: List of holiday dates in 'YYYY-MM-DD' format
        """
        super().__init__(
            calendar_id=calendar_id,
            credentials_path=credentials_path,
            slot_start_time=slot_start_time,
            slot_end_time=slot_end_time,
            time_between_slots=time_between_slots,
            lunch_start_time=lunch_start_time,
            lunch_end_time=lunch_end_time,
            duration=duration,
            date_value=date_value,
            timezone_code=timezone_code
        )
        
        self.holidays = set(holidays) if holidays else set()
        
    @property
    def is_weekend(self) -> bool:
        """Check if current date is a weekend"""
        return self.date_value.weekday() in self.WEEKEND_DAYS
    
    @property
    def is_holiday(self) -> bool:
        """Check if current date is a holiday"""
        return self.date_value.strftime("%Y-%m-%d") in self.holidays
    
    def add_holiday(self, holiday_date: str):
        """Add a holiday date"""
        try:
            # Validate date format
            datetime.strptime(holiday_date, "%Y-%m-%d")
            self.holidays.add(holiday_date)
        except ValueError:
            raise ValueError("Holiday date must be in 'YYYY-MM-DD' format")
    
    def remove_holiday(self, holiday_date: str):
        """Remove a holiday date"""
        self.holidays.discard(holiday_date)
    
    def get_holidays(self) -> List[str]:
        """Get list of all holidays"""
        return sorted(list(self.holidays))
    
    def is_working_day(self) -> bool:
        """Check if current date is a working day (not a holiday or weekend)"""
        return not (self.is_holiday or self.is_weekend)
    
    def get_next_working_day(self) -> str:
        """Get the next working day"""
        next_date = self.date_value + timedelta(days=1)
        while True:
            temp_instance = self.__class__(
                calendar_id=self.calendar_id,
                credentials_path="",  # Temporary instance doesn't need credentials
                date_value=next_date.strftime("%Y-%m-%d"),
                holidays=list(self.holidays)
            )
            if temp_instance.is_working_day():
                return next_date.strftime("%Y-%m-%d")
            next_date += timedelta(days=1)
    
    def get_available_slots(self, duration: int = None, requested_date: str = None) -> List[dict]:
        """Override get_available_slots to check for holidays and weekends"""
        check_date = requested_date or self.date_value.strftime("%Y-%m-%d")
        
        # Create temporary instance to check the requested date
        temp_instance = self.__class__(
            calendar_id=self.calendar_id,
            credentials_path="",  # Temporary instance doesn't need credentials
            date_value=check_date,
            holidays=list(self.holidays)
        )
        
        # If it's a holiday or weekend, return empty list
        if not temp_instance.is_working_day():
            return []
            
        # If it's a working day, use parent class method
        return super().get_available_slots(duration, requested_date)
    
    def get_date_info(self) -> Dict[str, bool]:
        """Get information about the current date"""
        return {
            "date": self.date_value.strftime("%Y-%m-%d"),
            "is_weekend": self.is_weekend,
            "is_holiday": self.is_holiday,
            "is_working_day": self.is_working_day()
        }
