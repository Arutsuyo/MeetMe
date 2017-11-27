import json
import logging

# Date handling 
import arrow # Replacement for datetime, based on moment.js
# import datetime # But we still need time
from dateutil import tz  # For interpreting local times

def process_events( events ):
    cal_events = []
    alldayrepeat = []
    for event in events['items']:
        # Skip via transparency
        if "transparency" in event and event["transparency"] == "transparent":
            continue
        try:
            cal_events.append({"name": event['summary'],
                            "start": event['start']['dateTime'],
                            "end": event['end']['dateTime']})
        except :
            try:
                # Clear Repeated all day events
                # They appear in the start and end
                if event['id'] in alldayrepeat:
                    continue
                cal_events.append({"name": event['summary'],
                            "start": event['start']['date'],
                            "end": event['start']['date']})
                alldayrepeat.append(event['id'])
            except :
                dumpObject(event, "SINGLEEVENT")
                raise
        # End Except
    # End event in events['items']:
    return cal_events
# End process_events()

def just_events(cal_events):
    events = []
    for list in cal_events:
        events.extend(list["Events"])
    return events


def build_free_list( event_list, startList, endList ):
    freeList = []
    for i in range(len(startList)):
        freeList.append({
            "Day" : startList[i].format("ddd MM/DD/YYYY"),
            "FreeBusy": make_free_busy_list(event_list[i]["Events"], 
                                            startList[i], 
                                            endList[i])
            })
    # End i in range(len(startList)):
    return freeList
# End build_free_list()

# Internal -DONT IMPORT-
def make_free_busy_list(events, fStart, fEnd):
    events_length = len(events)
    timeBlocks = []
    if events_length == 0:
        timeBlocks.append({
            "FB": "Free", # Free
            "S" : fStart.format("HH:mm"),
            "E" : fEnd.format("HH:mm")
            })
        return timeBlocks
    
    # Test to see if we have an allday
    for event in events:
        t0 = arrow.get(event['start']).format("HH:mm")
        t1 = arrow.get(event['end']).format("HH:mm")
        if t0 == "00:00" and t1 == "00:00":
            timeBlocks.append({
                "FB": "Busy", # Free
                "S" : fStart.format("HH:mm"),
                "E" : fEnd.format("HH:mm")
                })
            return timeBlocks

    eStart1 = arrow.get(events[0]['start'])
    eEnd1 = arrow.get(events[0]['end'])
    
    if fStart < eStart1:
        timeBlocks.append({
            "FB": "Free", # Free
            "S" : fStart.format("HH:mm"),
            "E" : eStart1.format("HH:mm")
            })
    if events_length == 1:
        timeBlocks.append({
            "FB": "Busy", # busy
            "S" : eStart1.format("HH:mm"),
            "E" : eEnd1.format("HH:mm")
            })
        if eEnd1 < fEnd:
            timeBlocks.append({
                "FB": "Free", # Free
                "S" : eEnd1.format("HH:mm"),
                "E" : fEnd.format("HH:mm")
                })
            return timeBlocks
    # End 1 event return
    
    for i in range(events_length):
        eStart = arrow.get(events[i]['start'])
        eEnd = arrow.get(events[i]['end'])
        timeBlocks.append({
            "FB": "Busy", # busy
            "S" : eStart.format("HH:mm"),
            "E" : eEnd.format("HH:mm")
            })
        if eEnd < fEnd:
            if i+1 < events_length:
                tStart = arrow.get(events[i+1]['start'])
                if tStart < fEnd and eEnd < tStart:
                    timeBlocks.append({
                        "FB": "Free", # Free
                        "S" : eEnd.format("HH:mm"),
                        "E" : tStart.format("HH:mm")
                        })
                # End tStart < fEnd:
            else:
                timeBlocks.append({
                        "FB": "Free", # Free
                        "S" : eEnd.format("HH:mm"),
                        "E" : fEnd.format("HH:mm")
                        })
            # End i+1 < events_length:
        # End eEnd < fEnd:
    # End i in range(events_length):
    count = 1
    total = len(timeBlocks)
    while count < total:
        if timeBlocks[count - 1]["FB"] == "Busy" and timeBlocks[count]["FB"] == "Busy":
            if timeBlocks[count - 1]["E"] >= timeBlocks[count]["S"]:
                timeBlocks[count]["S"] = timeBlocks[count - 1]["S"]
                del timeBlocks[count - 1]
                total = len(timeBlocks)
        else:
            count += 1
            
    return timeBlocks
    
##########################
# Utility Funciton for Dev
def dumpObject(obj, name):
    try:
        with open("./dump/"+ name +".json", 'w') as outfile:
            json.dump(obj, outfile)
    except :
        print("WARNING WARNING")
        print("Couldn't dump " + name)
        print(obj)
# End of Dev Functions
######################
