### DEBUG OPTIONS
DEBUG = True #Turn this False before submission
### End Debug

def dprint(output):
    if DEBUG:
        print("DB::"+ output)

# Date handling 
import arrow
from dateutil import tz

# Mongo database
from pymongo import MongoClient

class MongoDBManager:
    def __init__(self, MONGO_CLIENT_URL, DB_NAME, B_COLLECTION):
        """
        Initialize the database and establish a connection
        """
        try: 
            self.dbclient = MongoClient(MONGO_CLIENT_URL)
            self.db = getattr(self.dbclient, DB_NAME)
            self.collection = getattr(self.db, B_COLLECTION)
            dprint("Mongo Manager Initilized")
        except:
            print("ERROR: Failure opening database. Is Mongo running? Correct password?")
            raise

    def makeNewEvent(self, event_name, begin_date, begin_time,
                     end_date, end_time, event_hash):
        """
        Insert a new record into the collection for us to use
        """
        record = {"event_name": event_name,
                 "begin_date": begin_date,
                 "begin_time": begin_time,
                 "end_date": end_date,
                 "end_time": end_time,
                 "event_hash": event_hash}
        for record in self.collection.find({'event_hash' : event_hash}):
            dprint("Event already exists")
            return False
        self.collection.insert(record)
        return True
    
    def deleteEvent(self, event_hash):
        delCount = 0
        for record in self.collection.find({'event_hash' : event_hash}):
            res = self.collection.delete_one(record)
            delCount+=res.deleted_count
        for record in self.collection.find({'Event_Freebusy_Hash' : event_hash}):
            res = self.collection.delete_one(record)
            delCount+=res.deleted_count
        return delCount

    def getEventDetails(self, event_hash):
        """
        finds the Event via event_hash and returns the basic event details.
        """
        dprint("Checking for " + event_hash)
        Event = {}
        Event["status"] = False
        for record in self.collection.find({ "event_hash": event_hash }):
            print(record)
            Event["event_name"] = record["event_name"]
            Event["begin_date"] = record["begin_date"]
            Event["begin_time"] = record["begin_time"]
            Event["end_date"] = record["end_date"]
            Event["end_time"] = record["end_time"]
            Event["event_hash"] = record["event_hash"]
            Event["status"] = True
            print("Event:")
            print(Event)
            break
        return Event

    def get_insert_index(self, event_hash):
        """
        Finding next index funciton, thanks to Sam Champer
        for the function. Theory from Me
        """
        index = 0
        for record in self.collection.find(
            {"Event_Freebusy_Hash" : event_hash}, {"submit_index" : 1}):
            if record["submit_index"] > index:
                index = record["submit_index"]
        index+=1
        return index

    def submitFreeBusy(self, freebusy, event_hash):
        """
        Submits free/busy list to the server, which will track all entries and
        calculate event times possibilities based on all the entries.
        """
        record = {
            "Event_Freebusy_Hash": event_hash,
            "Timeblocks": freebusy,
            "submit_index" : self.get_insert_index(event_hash)
            }
        self.collection.insert(record)

    def calculate_event_times(self, event_hash):
        blocks = []
        for record in self.collection.find({ "Event_Freebusy_Hash": event_hash }):
            for day in record["Timeblocks"]:
                print("Day Dump")
                print(day)
                block = {"Day" : day["Day"],
                         "times" : []}
                for time in day["FreeBusy"]:
                    if time["FB"] == "Free":
                        block["times"].append({
                            "S" : time["S"],
                            "E" : time["E"]})
                    # End if
                # End For time
                blocks.append(block)
            # End For day
        # End For Record
        return blocks