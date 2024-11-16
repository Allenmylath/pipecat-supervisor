from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import os
import pytz

class IntakeProcessor:
    def __init__(self, context: OpenAILLMContext):
        print(f"Initializing context from IntakeProcessor")
        # Initialize calendar service
        self.calendar_service = self._init_calendar_service()
        # Store doctor schedules - could be fetched from database
        self.doctor_schedules = {
            "primary": "primary_calendar_id",  # Main calendar
            "Dr. Smith": "dr_smith_calendar_id",
            "Dr. Johnson": "dr_johnson_calendar_id",
            # Add more doctors as needed
        }
        self.APPOINTMENT_DURATION = 30  # minutes
        self.WORKING_HOURS = {
            'start': '09:00',
            'end': '17:00'
        }
        
        context.add_message(
            {
                "role": "system",
                "content": "You are Jessica, a telephone call agent for a company called Tri-County Health Services. Your job is to collect important information from the user before their doctor visit. You're talking to Chad Bailey. You should address the user by their first name and be polite and professional. You're not a medical professional, so you shouldn't provide any advice. Keep your responses short. To insert pauses, insert '-' where you need the pause. Use two question marks to emphasize questions. Start by introducing yourself. Then, ask the user to confirm their identity by telling you their birthday, including the year. When they answer with their birthday, call the verify_birthday function.",
            }
        )
        context.set_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "verify_birthday",
                        "description": "Use this function to verify the user has provided their correct birthday.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "birthday": {
                                    "type": "string",
                                    "description": "The user's birthdate, including the year. The user can provide it in any format, but convert it to YYYY-MM-DD format to call this function.",
                                }
                            },
                        },
                    },
                }
            ]
        )

    def _init_calendar_service(self):
        """Initialize Google Calendar API service"""
        api_key = os.environ.get('GOOGLE_CALENDAR_API_KEY')
        return build('calendar', 'v3', developerKey=api_key, static_discovery=False)

    async def verify_birthday(
        self, function_name, tool_call_id, args, llm, context, result_callback
    ):
        if args["birthday"] == "1990-01-01":
            context.set_tools(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "check_department_availability",
                            "description": "Check available departments and doctors",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "department": {
                                        "type": "string",
                                        "description": "Medical department name"
                                    }
                                },
                                "required": ["department"]
                            }
                        }
                    }
                ]
            )
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": "Great! Let's schedule your appointment. First, which department do you need to visit?? (Available departments: General Medicine, Cardiology, Orthopedics, Pediatrics)",
                    }
                ]
            )
        else:
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": "The user provided an incorrect birthday. Ask them for their birthday again. When they answer, call the verify_birthday function.",
                    }
                ]
            )

    async def check_department_availability(self, function_name, tool_call_id, args, llm, context, result_callback):
        department = args["department"]
        # Get doctors for the department (could be fetched from a database)
        department_doctors = self.get_department_doctors(department)
        
        context.set_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "get_available_slots",
                        "description": "Get available appointment slots for a specific date range",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "doctor": {
                                    "type": "string",
                                    "description": "Selected doctor's name"
                                },
                                "preferred_date": {
                                    "type": "string",
                                    "description": "Preferred date in YYYY-MM-DD format"
                                }
                            },
                            "required": ["doctor", "preferred_date"]
                        }
                    }
                }
            ]
        )
        
        doctors_list = ", ".join(department_doctors)
        await result_callback(
            [
                {
                    "role": "system",
                    "content": f"The available doctors in {department} are: {doctors_list}. Ask the user which doctor they prefer and their preferred appointment date??",
                }
            ]
        )

    async def get_available_slots(self, function_name, tool_call_id, args, llm, context, result_callback):
        doctor = args["doctor"]
        preferred_date = args["preferred_date"]
        
        # Get available time slots
        available_slots = await self.find_available_slots(doctor, preferred_date)
        
        if not available_slots:
            # No slots available, check next few days
            next_available = await self.find_next_available_day(doctor, preferred_date)
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": f"I apologize, but there are no available slots with {doctor} on {preferred_date}. The next available date is {next_available}. Would you like to see the available times for that date?? (Please ask the user and then call get_available_slots with the new date if they agree)",
                    }
                ]
            )
            return

        context.set_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "schedule_appointment",
                        "description": "Schedule the appointment with selected time slot",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "doctor": {
                                    "type": "string",
                                    "description": "Doctor's name"
                                },
                                "date": {
                                    "type": "string",
                                    "description": "Appointment date (YYYY-MM-DD)"
                                },
                                "time": {
                                    "type": "string",
                                    "description": "Selected time slot (HH:MM)"
                                }
                            },
                            "required": ["doctor", "date", "time"]
                        }
                    }
                }
            ]
        )

        slots_formatted = ", ".join([slot.strftime("%I:%M %p") for slot in available_slots])
        await result_callback(
            [
                {
                    "role": "system",
                    "content": f"The following time slots are available with {doctor} on {preferred_date}: {slots_formatted}. Which time would you prefer??",
                }
            ]
        )

    async def find_available_slots(self, doctor, date):
        """Find available time slots for a given doctor and date"""
        calendar_id = self.doctor_schedules.get(doctor)
        if not calendar_id:
            return []

        start_time = f"{date}T{self.WORKING_HOURS['start']}:00"
        end_time = f"{date}T{self.WORKING_HOURS['end']}:00"

        # Get existing events
        events_result = self.calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        # Generate all possible slots
        all_slots = []
        current = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
        end = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")
        
        while current + timedelta(minutes=self.APPOINTMENT_DURATION) <= end:
            slot_end = current + timedelta(minutes=self.APPOINTMENT_DURATION)
            is_available = True
            
            # Check if slot conflicts with any existing event
            for event in events:
                event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')))
                event_end = datetime.fromisoformat(event['end'].get('dateTime', event['end'].get('date')))
                
                if (current >= event_start and current < event_end) or \
                   (slot_end > event_start and slot_end <= event_end):
                    is_available = False
                    break
            
            if is_available:
                all_slots.append(current)
            
            current += timedelta(minutes=self.APPOINTMENT_DURATION)

        return all_slots

    async def find_next_available_day(self, doctor, start_date):
        """Find the next day with available slots"""
        current_date = datetime.strptime(start_date, "%Y-%m-%d")
        for _ in range(14):  # Look up to 14 days ahead
            current_date += timedelta(days=1)
            slots = await self.find_available_slots(doctor, current_date.strftime("%Y-%m-%d"))
            if slots:
                return current_date.strftime("%Y-%m-%d")
        return None

    async def schedule_appointment(self, function_name, tool_call_id, args, llm, context, result_callback):
        try:
            doctor = args['doctor']
            date = args['date']
            time = args['time']

            # Verify slot is still available
            available_slots = await self.find_available_slots(doctor, date)
            selected_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            
            if selected_time not in available_slots:
                await result_callback(
                    [
                        {
                            "role": "system",
                            "content": "I apologize, but that time slot is no longer available. Let me check for other available slots again. Please call get_available_slots with the same date.",
                        }
                    ]
                )
                return

            # Create the calendar event
            event = {
                'summary': f"Doctor Appointment - {doctor}",
                'description': f"Patient: Chad Bailey",
                'start': {
                    'dateTime': f"{date}T{time}:00",
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': (selected_time + timedelta(minutes=self.APPOINTMENT_DURATION)).isoformat(),
                    'timeZone': 'UTC',
                },
                'attendees': [
                    {'email': 'patient@example.com'},
                    {'email': f"{doctor.lower().replace(' ', '.')}@tricounty.com"}
                ],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},
                        {'method': 'popup', 'minutes': 60},
                    ],
                },
            }

            event = self.calendar_service.events().insert(
                calendarId=self.doctor_schedules[doctor],
                body=event,
                sendUpdates='all'
            ).execute()

            # Move to prescriptions after successful scheduling
            context.set_tools([self.get_prescriptions_tool()])
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": f"Perfect! Your appointment has been scheduled with {doctor} on {date} at {time}. You'll receive a confirmation email shortly. Now, let me ask about your current prescriptions. Please list all your current medications with their dosages.",
                    }
                ]
            )

        except Exception as e:
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": "I apologize, but there was an error scheduling your appointment. Let's try again. Please call get_available_slots with your preferred date.",
                    }
                ]
            )

    def get_department_doctors(self, department):
        """Get list of doctors for a department (demo data)"""
        doctors = {
            "General Medicine": ["Dr. Smith", "Dr. Johnson"],
            "Cardiology": ["Dr. Chen", "Dr. Patel"],
            "Orthopedics": ["Dr. Brown", "Dr. Davis"],
            "Pediatrics": ["Dr. Wilson", "Dr. Garcia"]
        }
        return doctors.get(department, [])

    # ... (rest of the original methods remain the same) ...
