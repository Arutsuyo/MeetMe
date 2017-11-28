# Flask Import
import flask
from flask import render_template
from flask import request
from flask import url_for
import uuid

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

# Mongo database
from pymongo import MongoClient

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
from eventProcessing import process_events, just_events, build_free_list, dumpObject

app = flask.Flask(__name__)
app.debug=CONFIG.DEBUG
app.logger.setLevel(logging.DEBUG)
app.secret_key=CONFIG.SECRET_KEY

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_KEY_FILE  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'

#############################
#
#  Pages (routed from URLs)
#
#############################

@app.route("/")
@app.route("/index")
def index():
  app.logger.debug("Entering index")
  if 'begin_date' not in flask.session:
    init_session_values()
  return render_template('index.html')

@app.route('/setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")  
    form = request.form.to_dict()
    print("Form:")
    print(form)

    flask.flash("Setrange gave us '{} {} - {} {}'".format(
      form['begin_date'], form['begin_time'], form['end_date'], form['end_time']))
    flask.session['begin_date'] = form['begin_date']
    flask.session['end_date'] = form['end_date']
    flask.session['begin_time'] = form['begin_time']
    flask.session['end_time'] = form['end_time']
    
    return flask.redirect(flask.url_for("choose"))

@app.route("/choose")
def choose():
    ## We'll need authorization to list calendars 
    ## I wanted to put what follows into a function, but had
    ## to pull it back here because the redirect has to be a
    ## 'return' 
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.g.calendars = list_calendars(gcal_service)
    return render_template('index.html')

@app.route("/getevents", methods=['POST'])
def getevents():
    """
    User chose calanders and we return the events
    """
    print("Entering getevents")  
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
    bd = flask.session['begin_date']
    bt = flask.session['begin_time']
    ed = flask.session['end_date']
    et = flask.session['end_time']
    startb = arrow.get(bd + " " + bt, "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    starte = arrow.get(ed + " " + bt, "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    endb = arrow.get(bd + " " + et, "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    ende = arrow.get(ed + " " + et, "YYYY-MM-DD HH:mm").replace(tzinfo='US/Pacific')
    startRange = []
    endRange = []
    for s in arrow.Arrow.range('day', startb, starte):
        startRange.append(s)
    for e in arrow.Arrow.range('day', endb, ende):
        endRange.append(e)

    if len(startRange) != len(endRange):
        print("Time Spans dont match, server error")
        raise
    
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
                "Events":   process_events( events ) 
                })
        # End id in validIDs:
    # End i in range(len(startRange)):
    
    eventList = just_events(cal_events)
    freelist = build_free_list(cal_events, startRange, endRange)
    
    # Finally add events to session
    flask.session['events'] = eventList
    flask.session['EventLength'] = len(eventList)
    flask.session['freebusy'] = freelist
    flask.flash("getevents gave us '{}' events".format(len(cal_events)))
    return flask.redirect(flask.url_for("index"))
# End getevents()


#############################
#
# MongoDB Functions
#
#############################

MONGO_CLIENT_URL = "mongodb://{}:{}@{}:{}/{}".format(CONFIG.DB_USER,
    CONFIG.DB_USER_PW,
    CONFIG.DB_HOST, 
    CONFIG.DB_PORT, 
    CONFIG.DB)

####
# Database connection per server process
###
try: 
    dbclient = MongoClient(MONGO_CLIENT_URL)
    db = getattr(dbclient, str(CONFIG.DB))
    collection = getattr(db, CONFIG.DB_COLLECTION)

except:
    print("Failure opening database.  Is Mongo running? Correct password?")
    sys.exit(1)

def get_memos():
    """
    Returns all memos in the database, in a form that
    can be inserted directly in the 'session' object.
    """
    records = []
    for record in collection.find({ "type": "dated_memo" }):
        record['date'] = arrow.get(record['date']).isoformat()
        record['visDate'] = humanize_arrow_date(record['date'])
        del record['_id']
        records.append(record)
    records.sort(key=lambda i: arrow.get(i['date']))
    return records 

def get_insert_index():
    """
    Finding next index funciton, thanks to Sam Champer
    for the function. Theory from Me
    """
    index = 0
    for record in collection.find():
        if record["index"] > index:
            index = record["index"]
    index+=1
    return index

def new_memo(input, date):
    record = { "type": "dated_memo", 
           "date":  date,
           "text": input,
           "index": get_insert_index()
          }
    collection.insert(record)

def del_memo(input):
    for record in collection.find({'index' : input}):
        res = collection.delete_one(record)
        return res.deleted_count
    return 0

######### Mongo Routing Functions #########

# Get current memo state
@app.route("/_getmemos")
def getmemos():
    allMemos = get_memos()
    result = {"memos" : allMemos}
    return flask.jsonify(result=result)

# Interface for creating memos
@app.route("/_create")
def create():
     """
     Get the arguments and create an entry from input
     """
     newMemo = request.args.get('newMemo', type=str)
     memoDate = request.args.get('inputDate', type=str)
     new_memo(newMemo, memoDate)
     app.logger.debug("inserted")
     result = {"status" : True}
     return flask.jsonify(result=result)

 # Interface for deleting memos
@app.route("/_delete")
def delete():
     """
     Get the arguments and create an entry from input
     """
     memoIndex = request.args.get('memoIndex', type=int)
     res = del_memo(memoIndex)
     app.logger.debug("deleted")
     result = {"deleted" : res}
     return flask.jsonify(result=result)

#############################
#
# End of MongoDB Functions
#
#############################


#############################
#
# Google Services Functions
#
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
    return flask.redirect(flask.url_for('choose'))

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

    if (credentials.invalid or
        credentials.access_token_expired):
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

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')     # We really should be using tz from browser
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    print("Arrow Floor:")
    print(tomorrow.floor('day').isoformat())
    print("Arrow Ceil:")
    print(nextweek.ceil('day').isoformat())
    print("Input")
    print("{} - {}".format(
        tomorrow.format("MM/DD/YYYY H:MM"),
        nextweek.format("MM/DD/YYYY H:MM")))
    flask.session["begin_date"] = tomorrow.floor('day').format("YYYY-MM-DD")
    flask.session["end_date"] = nextweek.ceil('day').format("YYYY-MM-DD")
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = tomorrow.floor('day').format("HH:mm")
    flask.session["end_time"] = nextweek.ceil('day').format("HH:mm")

####
#  Functions (NOT pages) that return some information
####
  
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

#############################
#
# End of Google Services Functions
#
#############################

#################
#
# Functions used within the Jinja templates
#
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
        return "(bad time)"


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0")
    
