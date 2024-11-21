class Appointment(Slot):
    def __init__(
        self,
        date: datetime.date,
        time: time,
        summary: Optional[str] = "New Appointment",
        email: Optional[str] = None,
        phone: Optional[str] = None,
        description: Optional[str] = None,
        business_start: time = time(9, 0),
        business_end: time = time(17, 0),
        duration: int = 30,
        calendar_id: str = 'johananddijo@gmail.com'
    ):
        """
        Initialize an appointment.
        
        Args:
            date: The date of the appointment
            time: The time of the appointment
            summary: Title of the appointment
            email: Contact email
            phone: Contact phone number
            description: Appointment description
            business_start: Start of business hours
            business_end: End of business hours
            duration: Duration in minutes
            calendar_id: Google Calendar ID
        """
        # Combine date and time into datetime object for parent class
        datetime_obj = datetime.combine(date, time)
        
        # Initialize parent Slot class
        super().__init__(
            datetime_obj=datetime_obj,
            business_start=business_start,
            business_end=business_end,
            duration=duration,
            calendar_id=calendar_id
        )
        
        # Store appointment details
        self.summary = summary
        self.email = email
        self.phone = phone
        self.description = description

    def book_appointment(self) -> Tuple[bool, Union[str, List[Slot]]]:
        """
        Book the appointment in Google Calendar.
        If booking fails, returns available slots for the same day.
        
        Returns:
            Tuple containing:
            - Success flag (bool)
            - Either success message (str) or list of available Slot objects
        """
        # Check if slot is valid
        is_valid, reasons = self.is_valid()
        if not is_valid:
            # Return available slots for the same day using parent class method
            return False, Slot.get_available_slots(
                date=self.datetime.date(),
                business_start=self.business_start,
                business_end=self.business_end,
                duration=self.duration,
                calendar_id=self.calendar_id
            )
            
        try:
            # Create event details
            event_body = {
                'summary': self.summary,
                'description': '\n'.join(filter(None, [
                    self.description,
                    f"Contact Email: {self.email}" if self.email else None,
                    f"Contact Phone: {self.phone}" if self.phone else None
                ])),
                'start': {
                    'dateTime': self.datetime.isoformat(),
                    'timeZone': 'Asia/Kolkata',
                },
                'end': {
                    'dateTime': (self.datetime + timedelta(minutes=self.duration)).isoformat(),
                    'timeZone': 'Asia/Kolkata',
                }
            }
            
            # Check for conflicts before booking
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=self.datetime.isoformat(),
                timeMax=(self.datetime + timedelta(minutes=self.duration)).isoformat(),
                singleEvents=True
            ).execute()
            
            if events_result.get('items', []):
                # Slot no longer available, return alternative slots
                return False, Slot.get_available_slots(
                    date=self.datetime.date(),
                    business_start=self.business_start,
                    business_end=business_end,
                    duration=self.duration,
                    calendar_id=self.calendar_id
                )
            
            # Book the appointment
            event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event_body
            ).execute()
            
            return True, f"Appointment successfully booked with ID: {event.get('id')}"
            
        except Exception as e:
            # Return available slots in case of any error
            return False, Slot.get_available_slots(
                date=self.datetime.date(),
                business_start=self.business_start,
                business_end=self.business_end,
                duration=self.duration,
                calendar_id=self.calendar_id
            )
