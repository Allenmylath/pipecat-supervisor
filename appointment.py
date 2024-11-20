from datetime import datetime, timedelta
from typing import List, Dict, Optional
from date import Date
import re

class Appointment(Date):
    def __init__(self, 
                 calendar_id: str,
                 credentials_path: str,
                 slot_start_time: str = Date.DEFAULT_START_TIME,
                 slot_end_time: str = Date.DEFAULT_END_TIME,
                 time_between_slots: int = 0,
                 lunch_start_time: str = Date.DEFAULT_LUNCH_START,
                 lunch_end_time: str = Date.DEFAULT_LUNCH_END,
                 duration: int = Date.DEFAULT_DURATION,
                 date_value: str = None,
                 timezone_code: str = 'IN',
                 holidays: List[str] = None):
        """
        Initialize Appointment class
        Inherits all parameters from Date class
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
            timezone_code=timezone_code,
            holidays=holidays
        )

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        if not email:
            return True  # Empty email is valid (optional)
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format"""
        if not phone:
            return True  # Empty phone is valid (optional)
        # Accepts formats: +1234567890, 1234567890, +91-1234567890
        pattern = r'^(\+?\d{1,3}[-.]?)?\d{10}$'
        return bool(re.match(pattern, phone))

    def format_phone_number(self, phone: str) -> str:
        """Format phone number to consistent format"""
        if not phone:
            return ""
        # Remove all non-digit characters except leading '+'
        formatted = ''.join(c for i, c in enumerate(phone) 
                          if c.isdigit() or (i == 0 and c == '+'))
        return formatted

    def get_next_available_slot_same_day(self, start_time: str = None) -> Optional[Dict]:
        """
        Find the next available slot on the same day after the given start time
        
        Parameters:
        start_time: Starting time to search from (HH:MM format)
        
        Returns:
        Dictionary containing slot information or None if no slots available
        """
        current_time = start_time or datetime.now(self.timezone).strftime("%H:%M")
        available_slots = self.get_available_slots()
        
        for slot in available_slots:
            if slot['start_time'] > current_time:
                return slot
                
        return None

    def get_next_date_same_slot(self, start_time: str, max_days: int = 30) -> Optional[Dict]:
        """
        Find the next available date for the same time slot
        
        Parameters:
        start_time: Desired time slot (HH:MM format)
        max_days: Maximum number of days to look ahead
        
        Returns:
        Dictionary containing slot information or None if no slots available
        """
        current_date = self.date_value
        for _ in range(max_days):
            next_date = current_date + timedelta(days=1)
            
            temp_instance = self.__class__(
                calendar_id=self.calendar_id,
                credentials_path=self.credentials_path,
                date_value=next_date.strftime("%Y-%m-%d"),
                holidays=list(self.holidays)
            )
            
            if not temp_instance.is_working_day():
                current_date = next_date
                continue
                
            if temp_instance.is_slot_available(start_time):
                return {
                    "date": next_date.strftime("%Y-%m-%d"),
                    "start_time": start_time,
                    "end_time": temp_instance.get_end_time(start_time),
                    "duration": self.duration
                }
                
            current_date = next_date
            
        return None

    def get_top_slots_next_days(self, days: int = 5, limit: int = 10) -> List[Dict]:
        """
        Get top available slots in the next specified number of days
        
        Parameters:
        days: Number of days to look ahead
        limit: Maximum number of slots to return
        
        Returns:
        List of dictionaries containing slot information
        """
        all_slots = []
        current_date = self.date_value
        
        for _ in range(days):
            temp_instance = self.__class__(
                calendar_id=self.calendar_id,
                credentials_path=self.credentials_path,
                date_value=current_date.strftime("%Y-%m-%d"),
                holidays=list(self.holidays)
            )
            
            if temp_instance.is_working_day():
                slots = temp_instance.get_available_slots()
                all_slots.extend(slots)
                
                if len(all_slots) >= limit:
                    return all_slots[:limit]
            
            current_date += timedelta(days=1)
        
        return all_slots[:limit]

    def book_slot(self, 
                 date_str: str, 
                 start_time: str, 
                 summary: str, 
                 description: str = None,
                 email: str = None,
                 phone: str = None,
                 attendee_emails: List[str] = None) -> Dict:
        """
        Book a slot in the calendar
        
        Parameters:
        date_str: Date for the appointment (YYYY-MM-DD format)
        start_time: Start time for the appointment (HH:MM format)
        summary: Title/summary of the appointment
        description: Detailed description of the appointment
        email: Optional contact email
        phone: Optional contact phone number
        attendee_emails: List of additional attendee email addresses
        
        Returns:
        Dictionary containing the created event details
        """
        # Validate contact information
        if not self.validate_email(email):
            raise ValueError("Invalid email format")
        if not self.validate_phone(phone):
            raise ValueError("Invalid phone number format")
            
        # Format phone number if provided
        formatted_phone = self.format_phone_number(phone) if phone else None
        
        # Validate date and time
        is_valid, message = self.is_valid_time(start_time, self.duration, date_str)
        if not is_valid:
            raise ValueError(f"Invalid slot: {message}")
            
        # Check availability
        if not self.is_slot_available(start_time, self.duration, date_str):
            raise ValueError("Slot is not available")
            
        # Create contact information string for description
        contact_info = ""
        if email or formatted_phone:
            contact_info = "\n\nContact Information:"
            if email:
                contact_info += f"\nEmail: {email}"
            if formatted_phone:
                contact_info += f"\nPhone: {formatted_phone}"
                
        # Combine description with contact info
        full_description = (description or "") + contact_info
            
        # Create event object
        event = {
            'summary': summary,
            'description': full_description,
            'start': {
                'dateTime': self._get_datetime_string(
                    datetime.strptime(date_str, "%Y-%m-%d").date(),
                    datetime.strptime(start_time, "%H:%M")
                ),
                'timeZone': self.timezone.zone
            },
            'end': {
                'dateTime': self._get_datetime_string(
                    datetime.strptime(date_str, "%Y-%m-%d").date(),
                    datetime.strptime(start_time, "%H:%M") + timedelta(minutes=self.duration)
                ),
                'timeZone': self.timezone.zone
            }
        }
        
        # Add attendees if provided
        all_attendees = []
        if email:
            all_attendees.append({'email': email})
        if attendee_emails:
            all_attendees.extend({'email': attendee} for attendee in attendee_emails)
            
        if all_attendees:
            event['attendees'] = all_attendees
            event['guestsCanModify'] = False
            event['guestsCanInviteOthers'] = False
        
        try:
            # Create event in Google Calendar
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event,
                sendUpdates='all' if all_attendees else 'none'
            ).execute()
            
            # Return formatted response
            return {
                'event_id': created_event['id'],
                'summary': created_event['summary'],
                'date': date_str,
                'start_time': start_time,
                'end_time': self.get_end_time(start_time),
                'duration': self.duration,
                'timezone': self.timezone.zone,
                'contact_email': email,
                'contact_phone': formatted_phone,
                'additional_attendees': attendee_emails or [],
                'status': created_event['status']
            }
            
        except Exception as e:
            raise Exception(f"Failed to book appointment: {str(e)}")

    def get_appointment_details(self, event_id: str) -> Dict:
        """
        Get details of a specific appointment
        
        Parameters:
        event_id: Google Calendar event ID
        
        Returns:
        Dictionary containing appointment details
        """
        try:
            event = self.service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            start_dt = datetime.fromisoformat(event['start']['dateTime'])
            
            # Extract contact information from description
            description = event.get('description', '')
            email = None
            phone = None
            
            # Parse description for contact information
            if 'Contact Information:' in description:
                contact_section = description.split('Contact Information:')[1]
                email_match = re.search(r'Email: (.+?)(?:\n|$)', contact_section)
                phone_match = re.search(r'Phone: (.+?)(?:\n|$)', contact_section)
                
                if email_match:
                    email = email_match.group(1).strip()
                if phone_match:
                    phone = phone_match.group(1).strip()
                
                # Remove contact information from description
                description = description.split('Contact Information:')[0].strip()
            
            return {
                'event_id': event['id'],
                'summary': event['summary'],
                'description': description,
                'date': start_dt.date().strftime("%Y-%m-%d"),
                'start_time': start_dt.strftime("%H:%M"),
                'end_time': datetime.fromisoformat(event['end']['dateTime']).strftime("%H:%M"),
                'timezone': event['start']['timeZone'],
                'contact_email': email,
                'contact_phone': phone,
                'additional_attendees': [attendee['email'] for attendee in event.get('attendees', []) 
                                      if email is None or attendee['email'] != email],
                'status': event['status']
            }
            
        except Exception as e:
            raise Exception(f"Failed to get appointment details: {str(e)}")
