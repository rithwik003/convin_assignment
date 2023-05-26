import os
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework.views import APIView

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class GoogleCalendarInitView(APIView):
    def get(self, request):
        flow = Flow.from_client_secrets_file(
            os.path.join(settings.BASE_DIR, 'client_secrets.json'),
            scopes=SCOPES,
            redirect_uri=request.build_absolute_uri('/rest/v1/calendar/redirect/')
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        request.session['google_auth_state'] = state
        return HttpResponseRedirect(authorization_url)

class GoogleCalendarRedirectView(APIView):
    def get(self, request):
        state = request.session.get('google_auth_state')
        flow = Flow.from_client_secrets_file(
            os.path.join(settings.BASE_DIR, 'client_secrets.json'),
            scopes=SCOPES,
            redirect_uri=request.build_absolute_uri('/rest/v1/calendar/redirect/'),
            state=state
        )
        authorization_response = request.build_absolute_uri()
        flow.fetch_token(authorization_response=authorization_response)

        if not request.user.is_authenticated:
            return HttpResponse("User not authenticated")

        # Save the credentials for future API calls
        credentials = flow.credentials
        request.user.google_calendar_credentials = credentials.to_json()
        request.user.save()

        # Redirect to a view that lists the events
        return HttpResponseRedirect('/rest/v1/calendar/events/')

class GoogleCalendarEventsView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return HttpResponse("User not authenticated")

        # Load saved credentials for the user
        credentials = Credentials.from_authorized_user_info(
            request.user.google_calendar_credentials
        )
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                return HttpResponse("Invalid credentials")

        # Create a Google Calendar API service
        service = build('calendar', 'v3', credentials=credentials)

        # Get the list of events from the user's calendar
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=10, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        # Process and return the events
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            event_list.append({
                'summary': event['summary'],
                'start': start
            })

        return JsonResponse(event_list, safe=False)
