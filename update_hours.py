import yaml
import os
import requests
import googlemaps
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from datetime import datetime, timedelta

# Read config
with open('places.yaml') as f:
    data = yaml.safe_load(f)

# Read secrets
places_api_key = os.environ.get('PLACES_API_KEY')
refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')
client_id = os.environ.get('GOOGLE_CLIENT_ID')
client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

# Get access token
token_response = requests.post("https://oauth2.googleapis.com/token", data={
    'client_id': client_id,
    'client_secret': client_secret,
    'refresh_token': refresh_token,
    'grant_type': 'refresh_token'
})
access_token = token_response.json()['access_token']

# Connect to APIs
gmaps = googlemaps.Client(key=places_api_key)
creds = Credentials(
    token=access_token,
    refresh_token=refresh_token,
    client_id=client_id,
    client_secret=client_secret,
    token_uri="https://oauth2.googleapis.com/token"
)
service = build('calendar', 'v3', credentials=creds)

# Process each business
today = datetime.now()
next_monday = today + timedelta(days=(7 - today.weekday()))

for place in data['places']:
    name = place['name']
    location = place['location']
    calendar_id = place['calendar_id']

    # Find Place ID
    places_result = gmaps.find_place(
        input=f"{name} {location}",
        input_type='textquery',
        fields=['place_id', 'name']
    )
    place_id = places_result['candidates'][0]['place_id']

    # Get opening hours
    place_details = gmaps.place(place_id=place_id, fields=['opening_hours'])
    opening_hours = place_details['result']['opening_hours']['periods']

    # Create or find calendar
    if not calendar_id:
        new_calendar = service.calendars().insert(body={
            'summary': f"{name} Opening Hours"
        }).execute()
        calendar_id = new_calendar['id']

    # Delete existing events for next week
    existing_events = service.events().list(
        calendarId=calendar_id,
        timeMin=next_monday.isoformat() + 'Z',
        timeMax=(next_monday + timedelta(days=7)).isoformat() + 'Z',
        singleEvents=True
    ).execute()

    for event in existing_events.get('items', []):
        service.events().delete(calendarId=calendar_id, eventId=event['id']).execute()

    # Write events
    for period in opening_hours:
        if 'close' not in period:
            continue
        day_offset = period['open']['day']
        open_time = period['open']['time']
        close_time = period['close']['time']
        event_date = next_monday + timedelta(days=day_offset - 1)

        event = {
            'summary': f"{name} Opening Hours",
            'start': {
                'dateTime': event_date.strftime(f'%Y-%m-%dT{open_time[:2]}:{open_time[2:]}:00'),
                'timeZone': 'Europe/London'
            },
            'end': {
                'dateTime': event_date.strftime(f'%Y-%m-%dT{close_time[:2]}:{close_time[2:]}:00'),
                'timeZone': 'Europe/London'
            }
        }
        service.events().insert(calendarId=calendar_id, body=event).execute()
    
    # Save calendar ID back to YAML
    place['calendar_id'] = calendar_id

# Write updated YAML
with open('places.yaml', 'w') as f:
    yaml.dump(data, f)
