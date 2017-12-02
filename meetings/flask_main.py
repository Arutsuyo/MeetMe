# Flask Import
import flask
from flask import g, render_template, request, url_for
import uuid
import urllib

import json
import logging

# Date handling 
import arrow
from dateutil import tz

# Google API for services 
from apiclient import discovery
# OAuth2  - Google library implementation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Mongo database Manager
from mongoManager import *

###
# Globals
###
import config
if __name__ == "__main__":
    CONFIG = config.configuration()
else:
    CONFIG = config.configuration(proxied=True)

###
# Import Event processing funcitons
###
from eventProcessing import process_events, just_events
from eventProcessing import build_free_list, dumpObject

### DEBUG OPTIONS
DEBUG = False #Turn this False before submission
### End Debug

def dprint(*args, **kwargs):
    if DEBUG:
        print("DB::", *args, **kwargs)

app = flask.Flask(__name__)
app.debug=CONFIG.DEBUG
app.logger.setLevel(logging.DEBUG)
app.secret_key=CONFIG.SECRET_KEY

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_KEY_FILE  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'

####
# Initialize Mongo
###
MONGO_CLIENT_URL = "mongodb://{}:{}@{}:{}/{}".format(CONFIG.DB_USER,
    CONFIG.DB_USER_PW,
    CONFIG.DB_HOST, 
    CONFIG.DB_PORT, 
    CONFIG.DB)
MM = MongoDBManager(MONGO_CLIENT_URL, str(CONFIG.DB), CONFIG.DB_COLLECTION)

#############################
#  Pages (routed from URLs)
#############################

@app.route("/")
@app.route("/index")
def index():
  app.logger.debug("Entering index")
  return render_template('Index.html')

@app.route("/Create")
def Create():
    """
    Main event creation page
    """
    app.logger.debug("Entering Create")
    flask.session.clear()
    init_session_values()
    return render_template('Create.html')

@app.route('/_setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")
    form = request.form.to_dict()
    dprint("Form:")
    dprint(form)
    
    flask.session["event_name"] = form['event_name']
    flask.session["begin_date"] = form['begin_date']
    flask.session["end_date"] = form['end_date']
    flask.session["begin_time"] = form['begin_time']
    flask.session["end_time"] = form['end_time']
    
    return flask.redirect(flask.url_for("Created"))

@app.route("/Created")
def Created():
    """
    Displays the input criteria for the event and asks the user to finalize
    """
    app.logger.debug("Entering Created")
    return render_template('Created.html')


@app.route("/_finalize")
def finalize_event():
    """
    Get the arguments and create an Event Entry
    """
    # Parse Arguments
    event_name = request.args.get('event_name', type=str)
    begin_date = request.args.get('begin_date', type=str)
    begin_time = request.args.get('begin_time', type=str)
    end_date = request.args.get('end_date', type=str)
    end_time = request.args.get('end_time', type=str)
    event_hash = request.args.get('event_hash', type=str)

    dprint("Finalize:Event Has recieved: " + str(event_hash))

    # Send the event to the MongoManager to create it
    ret = MM.makeNewEvent(event_name, begin_date, begin_time, end_date, end_time, event_hash)
    result = {"status" : False,
              "event_hash": event_hash}
    if ret:
        app.logger.debug("Event Created")
        result["status"] = True
    else:
        app.logger.debug("ERROR: Event Creation Failed!!!")
    return flask.jsonify(result=result)

@app.route("/_delete", methods=['POST'])
def delete_event():
    """
    Get the arguments and delete an Event Entry
    """
    app.logger.debug("Entering delete")  
    form = request.form.to_dict()
    dprint("Form:")
    dprint(form)
    
    hash = form['delete_hash']
    # Delete the given event and it's users info
    ret = MM.deleteEvent(hash)
    flask.session["deleted"] = True
    return flask.redirect(flask.url_for("Created"))


@app.route("/_token")
def assignToken():
    event_hash = request.args.get('event_hash', type=str)
    dprint("Do we have hash? " + event_hash)
    flask.session.clear()
    flask.session["event_hash"] = event_hash
    return flask.jsonify(result=True)

@app.route("/Token")
def join_hash():
    """
    User inputs Event token for retrieving information
    """
    app.logger.debug("Displaying token page")
    return render_template('Token.html')

@app.route("/View")
def veiw_hash():
    """
    Allows the user to submit an Event token and skip the gathering of times
    """
    app.logger.debug("Displaying view page")
    return render_template('View.html')

@app.route("/_getToken")
def getEventDetails():
    hash = request.args.get('event_hash', type=str)
    app.logger.debug("Checking database for: " + hash)

    details = MM.getEventDetails(hash)
    dprint("Recieved: " + str(details))
    if 'event_name' in details:
        flask.session.clear()
        details["status"] = True
        flask.session["event_name"] = details["event_name"]
        flask.session["begin_date"] = details["begin_date"]
        flask.session["begin_time"] = details["begin_time"]
        flask.session["end_date"]   = details["end_date"]
        flask.session["end_time"]   = details["end_time"]
        flask.session["event_hash"] = details["event_hash"]

    return flask.jsonify(result=details)


@app.route("/GetEvents")
def GetEvents():
    app.logger.debug("Entering GetEvents")
    if 'event_hash' not in flask.session:
        return flask.redirect(flask.url_for("Token"))
    return render_template('GetEvents.html')


@app.route("/join")
def join():
    
    event_hash = flask.session["event_hash"]
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.session["calendars"] = list_calendars(gcal_service)
    return render_template('GetEvents.html')


@app.route("/_getevents", methods=['POST'])
def get_events():
    """
    User chose calanders and we return the events
    """
    dprint("Entering getevents")  
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    
    incre = 0
    form = request.form.to_dict()
    validIDs = [id for id,checked in form.items() if checked == 'on']

    # Get the times / Dates
    bd = flask.session['begin_date']
    bt = flask.session['begin_time']
    ed = flask.session['end_date']
    et = flask.session['end_time']

    # Get the Spans
    startb = arrow.get(bd + " " + bt, "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    starte = arrow.get(ed + " " + bt, "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    endb = arrow.get(bd + " " + et,
                     "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    ende = arrow.get(ed + " " + et,
                     "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    startRange = []
    endRange = []
    # Pack Time ranges for each day
    for s in arrow.Arrow.range('day', startb, starte):
        startRange.append(s)
    for e in arrow.Arrow.range('day', endb, ende):
        endRange.append(e)

    if len(startRange) != len(endRange):
        print("Time Spans dont match, server error")
        raise
    
    # For each date/time range, ask for each calanders events
    cal_events = []
    for i in range(len(startRange)):
        for id in validIDs:
            events = gcal_service.events().list(calendarId=id,
                                            orderBy="startTime",
                                            timeMin=startRange[i],
                                            timeMax=endRange[i],
                                            singleEvents=True).execute()
            cal_events.append({ 
                "Start" :   startRange[i],
                "End"   :   endRange[i],
                # Process the events and return the list
                "Events":   process_events( events ) 
                })
        # End id in validIDs:
    # End i in range(len(startRange)):
    
    # Strip out the garbage
    eventList = just_events(cal_events)
    # Parse out a list of just the tiems and Free or Busy
    freelist = build_free_list(cal_events, startRange, endRange)
    
    # Finally add events to session
    flask.session['events'] = eventList
    flask.session['EventLength'] = len(eventList)
    flask.session['freebusy'] = freelist
    flask.flash("getevents gave us '{}' events".format(len(cal_events)))
    return render_template('GetEvents.html')
# End getevents()

@app.route("/_submitEvents")
def submitEvents():
    """
    Submitting Events to the database
    """
    app.logger.debug("Submitting Freebusy to database")
    event_hash = request.args.get('event_hash', type=str)
    
    if event_hash != flask.session['event_hash']:
        return flask.jsonify(result=False)
    event_name = flask.session["event_name"]
    
    # Submit the Users Free/Busy times to the server
    MM.submitFreeBusy(flask.session['freebusy'], event_hash)
    
    # Save Good Varibales
    bd = flask.session['begin_date']
    bt = flask.session['begin_time']
    ed = flask.session['end_date']
    et = flask.session['end_time']
    creds = flask.session["credentials"]
    app.logger.debug("Clearing session clutter")
    # Just keep the nessessary things, we don't need to hold the events anymore
    flask.session.clear()
    flask.session['begin_date'] = bd
    flask.session['begin_time'] = bt
    flask.session['end_date'] = ed
    flask.session['end_time'] = et
    flask.session["event_name"] = event_name
    flask.session['event_hash'] = event_hash
    flask.session["credentials"] = creds

    return flask.jsonify(result=True)

@app.route("/_invite")
def getInvite():
    # Create the invite link
    str = '<a href="mailto:name1@mail.com,name2@mail.com?subject=Your%20invited%20to%20Join%20an%20Event!&amp;body=Please%20visit%20the%20MeetMe!%20website%20and%20enter%20your%20invite%20token%20to%20join%20the%20event.%0AEvent%3A%20'
    str += urllib.parse.quote(flask.session["event_name"])
    str += '%0AToken%3A%20'
    str += urllib.parse.quote(flask.session["event_hash"])
    str += '">Invite guests</a>'
    dprint("Invite link:", str)
    res = {"inv" : str}
    return flask.jsonify(result=res)


@app.route("/_calcEventTimes")
def calcTimes():
    app.logger.debug("Entering _calcEventTimes")
    if 'event_hash' not in flask.session:
        result = {"status":False,
            "msg": "No Event info! Please go back to index and click create, join, or view"}
        return flask.jsonify(result=result)
    if 'begin_date' not in flask.session:
        # This is mostly here since view could only have the 
        # token in session and not the other details
        details = MM.getEventDetails(flask.session['event_hash'])
        flask.session["event_name"] = details["event_name"]
        flask.session["begin_date"] = details["begin_date"]
        flask.session["begin_time"] = details["begin_time"]
        flask.session["end_date"]   = details["end_date"]
        flask.session["end_time"]   = details["end_time"]

    # Get the Times that the event can happen from the user times
    flask.session["Event_Times"] = MM.calculate_event_times(flask.session['event_hash'])
    dprint("Calculated Available Event Times")
    dprint(flask.session["Event_Times"])
    # The thrack the number of users that have submitted
    flask.session["num_invites"] = MM.get_insert_index(flask.session['event_hash'])

    
    result = {"status":True}
    if len(flask.session["Event_Times"]) == 0:
        result = {"status":False,
                "msg": "No Times Found"}
    else:
        flask.session["Event_Times"] = flask.session["Event_Times"][0]
    return flask.jsonify(result=result)

@app.route("/EventInfo")
def eventInfo():
    # When this loadds it will callback to /_calcEventTimes
    
    app.logger.debug("Entering EventInfo")
    return render_template('EventInfo.html')

#############################
# Google Services Functions
#############################

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
  else:
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    app.logger.debug("Got credentials")
    return flask.redirect(flask.url_for('join'))

def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value. 
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])
    
    if credentials.invalid:
      return None
    return credentials

def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service

#### END OF GOOGLE HELPER FUNCTIONS ####

####
#  Functions (NOT pages) that return some information
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')     # We really should be using tz from browser
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    dprint("Arrow Floor:")
    dprint(tomorrow.floor('day').isoformat())
    dprint("Arrow Ceil:")
    dprint(nextweek.ceil('day').isoformat())
    dprint("Input")
    dprint("{} - {}".format(
        tomorrow.format("MM/DD/YYYY H:MM"),
        nextweek.format("MM/DD/YYYY H:MM")))
    flask.session["begin_date"] = tomorrow.floor('day').format("YYYY-MM-DD")
    flask.session["end_date"] = nextweek.ceil('day').format("YYYY-MM-DD")
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = tomorrow.floor('day').format("HH:mm")
    flask.session["end_time"] = nextweek.ceil('day').format("HH:mm")

def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])
  
def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict.
    The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")  
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]
    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal: 
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]
        
        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)

#################
# Functions used within the Jinja templates
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try: 
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        print("ServerError::Time: " + str(time))
        return "(bad time)"


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0")
    
