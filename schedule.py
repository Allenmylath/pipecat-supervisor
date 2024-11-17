import os
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

class ClinicAppointment:
    def __init__(self):
        # Hardcoded clinic and patient settings
        self.working_hours = {
            'start': 10,    # 10 AM
            'end': 17,      # 5 PM
            'lunch_start': 13,  # 1 PM
            'lunch_end': 14     # 2 PM
        }
        self.slot_duration = 30  # minutes
        self.timezone = 'America/New_York'
        self.patient_name = "Chad Bailey"
        self.patient_phone = "1234567890"
        
        # Google Calendar settings from environment variables
        self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        self.service = self.setup_calendar()

    def setup_calendar(self):
        """Setup Google Calendar service using service account credentials"""
        try:
            credentials_json = os.getenv('GOOGLE_CREDENTIALS')
            if not credentials_json:
                return None
            
            credentials_info = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            return build('calendar', 'v3', credentials=credentials)
            
        except Exception as e:
            print(f"Calendar setup error: {str(e)}")
            return None

    def get_available_slots(self, date):
        """Get available slots for a given date"""
        if not self.service:
            return "I apologize, but our scheduling system is currently unavailable. Please try again later."

        if date.weekday() >= 5:
            return "I apologize, but we don't have any appointments available on weekends. Would you like to check availability for the next working day?"

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

        booked_times = []
        for event in events.get('items', []):
            start = datetime.fromisoformat(event['start']['dateTime'].replace('Z', ''))
            booked_times.append(start.strftime('%H:%M'))

        available_slots = []
        current_time = datetime.combine(date, datetime.min.time().replace(hour=self.working_hours['start']))
        
        while current_time.hour < self.working_hours['end']:
            time_str = current_time.strftime('%H:%M')
            
            if current_time.hour == self.working_hours['lunch_start']:
                current_time = current_time.replace(hour=self.working_hours['lunch_end'])
                continue
                
            if time_str not in booked_times:
                available_slots.append(time_str)
                
            current_time += timedelta(minutes=self.slot_duration)

        if not available_slots:
            return f"I'm sorry, but all appointments are booked for {date.strftime('%A, %B %d')}. Would you like to check availability for another day?"

        formatted_slots = [datetime.strptime(time, '%H:%M').strftime('%I:%M %p') for time in available_slots]
        slots_text = ", ".join(formatted_slots)
        
        return f"For {date.strftime('%A, %B %d')}, we have the following appointments available: {slots_text}"

    def book_appointment(self, date, time_str):
        """Book an appointment for given date and time"""
        if not self.service:
            return "I apologize, but our scheduling system is currently unavailable. Please try again later."

        try:
            try:
                time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                time = datetime.strptime(time_str, '%I:%M %p').time()
            appointment_datetime = datetime.combine(date, time)
        except ValueError:
            return "I couldn't understand that time format. Please specify the time as either HH:MM (like 14:30) or HH:MM AM/PM (like 2:30 PM)."

        if date.weekday() >= 5:
            return "I apologize, but we don't schedule appointments on weekends. Would you like to book for a weekday instead?"

        if (appointment_datetime.hour < self.working_hours['start'] or 
            appointment_datetime.hour >= self.working_hours['end']):
            return f"I apologize, but we only schedule appointments between {self.working_hours['start']}:00 AM and {self.working_hours['end']-12}:00 PM. Would you like to choose a different time?"

        if (appointment_datetime.hour == self.working_hours['lunch_start']):
            return "I apologize, but that time falls during our lunch break from 1:00 PM to 2:00 PM. Would you like to choose a different time?"

        try:
            events = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=appointment_datetime.isoformat() + 'Z',
                timeMax=(appointment_datetime + timedelta(minutes=self.slot_duration)).isoformat() + 'Z',
                singleEvents=True
            ).execute()

            if events.get('items', []):
                return f"I apologize, but the {appointment_datetime.strftime('%I:%M %p')} slot is no longer available. Would you like to check other available times?"

            event = {
                'summary': f'Patient: {self.patient_name}',
                'description': f'Phone: {self.patient_phone}',
                'start': {
                    'dateTime': appointment_datetime.isoformat(),
                    'timeZone': self.timezone,
                },
                'end': {
                    'dateTime': (appointment_datetime + timedelta(minutes=self.slot_duration)).isoformat(),
                    'timeZone': self.timezone,
                }
            }

            self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
            return f"Great! I've booked your appointment for {date.strftime('%A, %B %d')} at {appointment_datetime.strftime('%I:%M %p')}. Please arrive 10 minutes early for your appointment. If you need to cancel or reschedule, please call us at least 24 hours in advance."

        except Exception as e:
            print(f"Booking error: {str(e)}")
            return "I'm having trouble booking the appointment right now. Please try again in a moment."

    def get_next_available_slots(self, start_date, num_slots=5):
        """Get next available slots starting from given date"""
        if not self.service:
            return "I apologize, but our scheduling system is currently unavailable. Please try again later."

        available_slots = []
        current_date = start_date
        days_checked = 0
        response_text = "Here are the next available appointments:\n"
        
        while len(available_slots) < num_slots and days_checked < 10:
            if current_date.weekday() < 5:
                day_slots = self.get_available_slots(current_date)
                if not day_slots.startswith("I apologize") and not day_slots.startswith("I'm having trouble"):
                    response_text += f"{day_slots}\n"
                    break
            
            current_date += timedelta(days=1)
            days_checked += 1

        if days_checked >= 10:
            return "I apologize, but I couldn't find any available appointments in the next 10 days. Would you like to check availability further in the future?"

        return response_text
