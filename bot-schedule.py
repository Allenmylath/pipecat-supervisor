from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import os

class IntakeProcessor:
    def __init__(self, context: OpenAILLMContext):
        print(f"Initializing context from IntakeProcessor")
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
        
        # Initialize Google Calendar API
        self.calendar_service = self._init_calendar_service()

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
                            "name": "schedule_appointment",
                            "description": "Schedule a doctor appointment after collecting appointment details",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "date": {
                                        "type": "string",
                                        "description": "Appointment date in YYYY-MM-DD format"
                                    },
                                    "time": {
                                        "type": "string",
                                        "description": "Appointment time in HH:MM format (24-hour)"
                                    },
                                    "doctor": {
                                        "type": "string",
                                        "description": "Name of the doctor"
                                    },
                                    "department": {
                                        "type": "string",
                                        "description": "Medical department for the appointment"
                                    }
                                },
                                "required": ["date", "time", "doctor", "department"]
                            }
                        }
                    }
                ]
            )
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": "Great! Now let's schedule your appointment. Ask the following questions in sequence:\n1. What date would you prefer for your appointment??\n2. What time works best for you??\n3. Do you have a preferred doctor??\n4. Which department do you need to visit??\nAfter collecting all details, call the schedule_appointment function.",
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

    async def schedule_appointment(self, function_name, tool_call_id, args, llm, context, result_callback):
        try:
            # Format datetime for Google Calendar
            start_datetime = f"{args['date']}T{args['time']}:00"
            end_datetime = (datetime.fromisoformat(start_datetime) + timedelta(hours=1)).isoformat()

            event = {
                'summary': f"Doctor Appointment - {args['doctor']}",
                'description': f"Department: {args['department']}\nPatient: Chad Bailey",
                'start': {
                    'dateTime': start_datetime,
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_datetime,
                    'timeZone': 'UTC',
                },
                'attendees': [
                    {'email': 'patient@example.com'},  # Replace with actual email
                    {'email': f"{args['doctor'].lower().replace(' ', '.')}@tricounty.com"}  # Doctor's email
                ],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},
                        {'method': 'popup', 'minutes': 60},
                    ],
                },
            }

            event = self.calendar_service.events().insert(calendarId='primary', body=event).execute()
            
            # After successful scheduling, move to prescriptions
            context.set_tools(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "list_prescriptions",
                            "description": "Once the user has provided a list of their prescription medications, call this function.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "prescriptions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "medication": {
                                                    "type": "string",
                                                    "description": "The medication's name",
                                                },
                                                "dosage": {
                                                    "type": "string",
                                                    "description": "The prescription's dosage",
                                                },
                                            },
                                        },
                                    }
                                },
                            },
                        },
                    }
                ]
            )
            
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": f"The appointment has been scheduled successfully for {args['date']} at {args['time']} with Dr. {args['doctor']}. Now, ask the user to list their current prescriptions. Each prescription needs to have a medication name and a dosage. Do not call the list_prescriptions function with any unknown dosages.",
                    }
                ]
            )

        except Exception as e:
            await result_callback(
                [
                    {
                        "role": "system",
                        "content": f"There was an error scheduling the appointment. Please ask the user to provide their preferred appointment date and time again.",
                    }
                ]
            )

    # ... rest of the original methods remain the same ...
