from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import os

class IntakeProcessor:
    def __init__(self, context: OpenAILLMContext):
        print(f"Initializing context from IntakeProcessor")
        # Initialize calendar service
        self.calendar_service = self._init_calendar_service()
        
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
            context.set_tools([
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
                    }
                }
            ])
            await result_callback([
                {
                    "role": "system",
                    "content": "Ask the user to list their current prescriptions. Each prescription needs to have a medication name and a dosage. Do not call the list_prescriptions function with any unknown dosages.",
                }
            ])

    async def start_prescriptions(self, function_name, llm, context):
        print(f"!!! doing start prescriptions")
        context.set_tools([
            {
                "type": "function",
                "function": {
                    "name": "list_allergies",
                    "description": "Once the user has provided a list of their allergies, call this function.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "allergies": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "What the user is allergic to",
                                        }
                                    },
                                },
                            }
                        },
                    },
                }
            }
        ])
        context.add_message(
            {
                "role": "system",
                "content": "Next, ask the user if they have any allergies. Once they have listed their allergies or confirmed they don't have any, call the list_allergies function.",
            }
        )
        await llm.process_frame(OpenAILLMContextFrame(context), FrameDirection.DOWNSTREAM)

    async def start_conditions(self, function_name, llm, context):
        print("!!! doing start conditions")
        context.set_tools([
            {
                "type": "function",
                "function": {
                    "name": "list_conditions",
                    "description": "Once the user has provided a list of their medical conditions, call this function.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "conditions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "The user's medical condition",
                                        }
                                    },
                                },
                            }
                        },
                    },
                }
            }
        ])
        context.add_message({
            "role": "system",
            "content": "Now ask the user if they have any medical conditions the doctor should know about. Once they've answered the question or confirmed they don't have any, call the list_conditions function.",
        })
        await llm.process_frame(OpenAILLMContextFrame(context), FrameDirection.DOWNSTREAM)

    async def start_visit_reasons(self, function_name, llm, context):
        print("!!! doing start visit reasons")
        context.set_tools([
            {
                "type": "function",
                "function": {
                    "name": "process_visit_reason",
                    "description": "Process the visit reason and determine appropriate department",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "visit_reason": {
                                "type": "string",
                                "description": "The reason for visiting the doctor"
                            }
                        },
                        "required": ["visit_reason"]
                    }
                }
            }
        ])
        context.add_message({
            "role": "system",
            "content": "Ask the user why they want to visit the doctor today. After they explain their condition, call the process_visit_reason function.",
        })
        await llm.process_frame(OpenAILLMContextFrame(context), FrameDirection.DOWNSTREAM)

    async def process_visit_reason(self, function_name, tool_call_id, args, llm, context, result_callback):
        # Map conditions to departments
        department = self.determine_department(args["visit_reason"])
        
        # Get available slots for the department
        slots = await self.get_department_availability(department)
        
        context.set_tools([
            {
                "type": "function",
                "function": {
                    "name": "schedule_appointment",
                    "description": "Schedule the appointment for the determined department",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "slot": {
                                "type": "string",
                                "description": "Selected time slot (YYYY-MM-DD HH:MM format)"
                            },
                            "department": {
                                "type": "string",
                                "description": "Medical department"
                            }
                        },
                        "required": ["slot", "department"]
                    }
                }
            }
        ])

        slots_formatted = "\n".join([f"- {slot}" for slot in slots])
        await result_callback([
            {
                "role": "system",
                "content": f"Based on your condition, I'll schedule you with our {department} department. Here are the available appointment slots:\n\n{slots_formatted}\n\nWhich time works best for you?? When the user selects a slot, call schedule_appointment with the chosen slot and department.",
            }
        ])

    def determine_department(self, visit_reason):
        """Determine appropriate department based on visit reason"""
        reason_lower = visit_reason.lower()
        
        # Simple keyword matching - could be made more sophisticated
        if any(word in reason_lower for word in ['heart', 'chest pain', 'blood pressure']):
            return 'Cardiology'
        elif any(word in reason_lower for word in ['bone', 'joint', 'back pain', 'muscle']):
            return 'Orthopedics'
        elif any(word in reason_lower for word in ['child', 'kid', 'baby']):
            return 'Pediatrics'
        else:
            return 'General Medicine'

    async def get_department_availability(self, department):
        """Get available slots for the department"""
        # Get next 5 business days
        slots = []
        current_date = datetime.now()
        
        for _ in range(5):
            if current_date.weekday() < 5:  # Monday to Friday
                for hour in range(9, 17):  # 9 AM to 5 PM
                    slot_time = current_date.replace(hour=hour, minute=0)
                    # Check if slot is available in Google Calendar
                    if await self.is_slot_available(department, slot_time):
                        slots.append(slot_time.strftime("%Y-%m-%d %H:%M"))
            current_date += timedelta(days=1)
        
        return slots

    async def is_slot_available(self, department, slot_time):
        """Check if a time slot is available in Google Calendar"""
        try:
            calendar_id = f"{department.lower()}@tricounty.com"
            start_time = slot_time.isoformat() + 'Z'
            end_time = (slot_time + timedelta(hours=1)).isoformat() + 'Z'
            
            events_result = self.calendar_service.events().list(
                calendarId=calendar_id,
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True
            ).execute()
            
            return len(events_result.get('items', [])) == 0
            
        except Exception as e:
            print(f"Error checking calendar availability: {e}")
            return False

    async def schedule_appointment(self, function_name, tool_call_id, args, llm, context, result_callback):
        try:
            slot = datetime.strptime(args["slot"], "%Y-%m-%d %H:%M")
            department = args["department"]
            
            event = {
                'summary': f"{department} Appointment - Chad Bailey",
                'description': "Regular checkup",
                'start': {
                    'dateTime': slot.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': (slot + timedelta(hours=1)).isoformat(),
                    'timeZone': 'UTC',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},
                        {'method': 'popup', 'minutes': 60},
                    ],
                },
            }

            await self.calendar_service.events().insert(
                calendarId=f"{department.lower()}@tricounty.com",
                body=event,
                sendUpdates='all'
            ).execute()

            # Move to finish
            context.set_tools([])
            await result_callback([
                {
                    "role": "system",
                    "content": f"Perfect! I've scheduled your appointment with {department} for {args['slot']}. You'll receive a confirmation email shortly. Thank you for choosing Tri-County Health Services. Have a great day!",
                }
            ])

        except Exception as e:
            await result_callback([
                {
                    "role": "system",
                    "content": "I apologize, but there was an error scheduling your appointment. Please try selecting a different time slot.",
                }
            ])

    async def save_data(self, function_name, tool_call_id, args, llm, context, result_callback):
        logger.info(f"Saving data: {args}")
        
        user_ref = db.collection('users').document('chad_bailey')

        if function_name == "list_prescriptions":
            user_ref.update({"prescriptions": args["prescriptions"]})
        elif function_name == "list_allergies":
            user_ref.update({"allergies": args["allergies"]})
        elif function_name == "list_conditions":
            user_ref.update({"conditions": args["conditions"]})
        elif function_name == "process_visit_reason":
            user_ref.update({"visit_reason": args["visit_reason"]})

        logger.info(f"Data saved to Firebase for function: {function_name}")
        await result_callback(None)
