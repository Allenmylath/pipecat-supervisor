from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os.path

class ClinicAppointment:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/calendar']
        self.calendar_id = 'primary'  # Clinic's primary calendar
        self.working_hours = {
            'start': 10,  # 10 AM
            'end': 17,    # 5 PM
            'lunch_start': 13,  # 1 PM
            'lunch_end': 14     # 2 PM
        }
        self.slot_duration = 30  # minutes
        self.service = self.setup_calendar()

    def setup_calendar(self):
        """Setup Google Calendar service - only needs to be done once for the clinic"""
        creds = None
        if os.path.exists('clinic_token.pickle'):
            with open('clinic_token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'clinic_credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
            with open('clinic_token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('calendar', 'v3', credentials=creds)

    def get_available_slots(self, date):
        """Get available slots for a given date"""
        if date.weekday() >= 5:  # Weekend check
            return "I apologize, but we don't have any appointments available on weekends. Would you like to check availability for the next working day?"

        # Get existing appointments
        start_time = datetime.combine(date, datetime.min.time())
        end_time = datetime.combine(date, datetime.max.time())
        
        try:
            events = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_time.isoformat() + 'Z',
                timeMax=end_time.isoformat() + 'Z',
                singleEvents=True
            ).execute()
        except Exception:
            return "I'm having trouble checking the calendar right now. Please try again in a moment."

        # Track booked slots
        booked_times = []
        for event in events.get('items', []):
            start = datetime.fromisoformat(event['start']['dateTime'].replace('Z', ''))
            booked_times.append(start.strftime('%H:%M'))

        # Generate available slots
        available_slots = []
        current_time = datetime.combine(date, datetime.min.time().replace(hour=self.working_hours['start']))
        
        while current_time.hour < self.working_hours['end']:
            time_str = current_time.strftime('%H:%M')
            
            # Skip lunch break
            if current_time.hour == self.working_hours['lunch_start']:
                current_time = current_time.replace(hour=self.working_hours['lunch_end'])
                continue
                
            if time_str not in booked_times:
                available_slots.append(time_str)
                
            current_time += timedelta(minutes=self.slot_duration)

        if not available_slots:
            return f"I'm sorry, but all appointments are booked for {date.strftime('%A, %B %d')}. Would you like to check availability for another day?"

        # Format times in 12-hour format for easier reading
        formatted_slots = [datetime.strptime(time, '%H:%M').strftime('%I:%M %p') for time in available_slots]
        slots_text = ", ".join(formatted_slots)
        
        return f"For {date.strftime('%A, %B %d')}, we have the following appointments available: {slots_text}"

    def book_appointment(self, date, time_str, patient_name, phone_number):
        """Book an appointment for given date and time"""
        # Convert time string to datetime
        try:
            # Handle both 24-hour and 12-hour time formats
            try:
                time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                time = datetime.strptime(time_str, '%I:%M %p').time()
            appointment_datetime = datetime.combine(date, time)
        except ValueError:
            return "I couldn't understand that time format. Please specify the time as either HH:MM (like 14:30) or HH:MM AM/PM (like 2:30 PM)."

        # Validation checks
        if date.weekday() >= 5:
            return "I apologize, but we don't schedule appointments on weekends. Would you like to book for a weekday instead?"

        if (appointment_datetime.hour < self.working_hours['start'] or 
            appointment_datetime.hour >= self.working_hours['end']):
            return f"I apologize, but we only schedule appointments between {self.working_hours['start']}:00 AM and {self.working_hours['end']-12}:00 PM. Would you like to choose a different time?"

        if (appointment_datetime.hour == self.working_hours['lunch_start']):
            return "I apologize, but that time falls during our lunch break from 1:00 PM to 2:00 PM. Would you like to choose a different time?"

        # Check availability
        try:
            events = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=appointment_datetime.isoformat() + 'Z',
                timeMax=(appointment_datetime + timedelta(minutes=self.slot_duration)).isoformat() + 'Z',
                singleEvents=True
            ).execute()

            if events.get('items', []):
                return f"I apologize, but the {appointment_datetime.strftime('%I:%M %p')} slot is no longer available. Would you like to check other available times?"

            # Create calendar event
            event = {
                'summary': f'Patient: {patient_name}',
                'description': f'Phone: {phone_number}',
                'start': {
                    'dateTime': appointment_datetime.isoformat(),
                    'timeZone': 'America/New_York',
                },
                'end': {
                    'dateTime': (appointment_datetime + timedelta(minutes=self.slot_duration)).isoformat(),
                    'timeZone': 'America/New_York',
                }
            }

            self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
            return f"Great! I've booked your appointment for {date.strftime('%A, %B %d')} at {appointment_datetime.strftime('%I:%M %p')}. Please arrive 10 minutes early for your appointment. If you need to cancel or reschedule, please call us at least 24 hours in advance."

        except Exception:
            return "I'm having trouble booking the appointment right now. Please try again in a moment."

    def get_next_available_slots(self, start_date, num_slots=5):
        """Get next available slots starting from given date"""
        available_slots = []
        current_date = start_date
        days_checked = 0
        response_text = "Here are the next available appointments:\n"
        
        while len(available_slots) < num_slots and days_checked < 10:  # Look up to 10 days ahead
            if current_date.weekday() < 5:  # Weekday
                day_slots = self.get_available_slots(current_date)
                if not day_slots.startswith("I apologize") and not day_slots.startswith("I'm having trouble"):
                    response_text += f"{day_slots}\n"
                    break  # Show only first day with available slots
            
            current_date += timedelta(days=1)
            days_checked += 1

        if days_checked >= 10:
            return "I apologize, but I couldn't find any available appointments in the next 10 days. Would you like to check availability further in the future?"

        return response_text
