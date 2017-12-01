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
        dprint("Deleting Event")
        res = self.collection.delete_many({'event_hash' : event_hash})
        delCount+=res.deleted_count
        dprint("Deleting User FreeBusy's")
        res = self.collection.delete_many({'Event_Freebusy_Hash' : event_hash})
        delCount+=res.deleted_count
        dprint("Deleted " + str(delCount) + " records")
        return delCount

    def getEventDetails(self, event_hash):
        """
        finds the Event via event_hash and returns the basic event details.
        """
        dprint("Checking for " + event_hash)
        Event = {}
        Event["status"] = False
        for record in self.collection.find({ "event_hash": event_hash }):
            dprint(record)
            Event["event_name"] = record["event_name"]
            Event["begin_date"] = record["begin_date"]
            Event["begin_time"] = record["begin_time"]
            Event["end_date"] = record["end_date"]
            Event["end_time"] = record["end_time"]
            Event["event_hash"] = record["event_hash"]
            Event["status"] = True
            dprint("Event:")
            dprint(Event)
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

        Details = self.getEventDetails(event_hash)

        schedules = []
        for record in self.collection.find({ "Event_Freebusy_Hash": event_hash }):
            blocks = []
            for day in record["Timeblocks"]:
                dprint("Day Dump")
                dprint(day)
                block = {"Day" : day["Day"],
                         "FreeBusy" : []}
                for time in day["FreeBusy"]:
                    if time["FB"] == "Busy":
                        block["FreeBusy"].append({
                            "S" : time["S"],
                            "E" : time["E"]})
                    # End if
                # End For time
                blocks.append(block)
            # End For day
            schedules.append(blocks)
        # End For Record
        
        totalSchedules = len(schedules)
        if totalSchedules == 0:
            return schedules
        
        while totalSchedules > 1:
            sched1 = schedules[0]
            sched2 = schedules[1]
            schedules[0] = self.mergeSchedules(sched1, sched2)
            del schedules[1]
            totalSchedules = len(schedules)
        # End For Schedule

        schedules[0] = self.flipSchedule(schedules[0],
                                      Details["begin_time"],
                                      Details["end_time"])

        return schedules

    def mergeSchedules(self, schedule1, schedule2):
        dprint("mergeSchedules\nDumping pre merged schedules\nSchedule 1")
        dprint(schedule1)
        dprint("Schedule 2")
        dprint(schedule2)
        for day1 in schedule1:
            for day2 in schedule2:
                if day1["Day"] == day2["Day"]:
                    FB1 = day1["FreeBusy"]
                    FB2 = day2["FreeBusy"]

                    index1 = 0
                    index2 = 0
                    total1 = len(FB1)
                    total2 = len(FB2)
                    while index1 < total1:
                        while index2 < total2:

                            # Case 0
                            if (FB1[index1]["S"] == FB2[index2]["S"] and
                                FB2[index2]["E"] == FB1[index1]["E"]):
                                dprint("Case0")
                                del FB2[index2]
                                total2 = len(FB2)
                                continue

                            # Case 1 (Handle next pass)
                            if FB2[index2]["E"] < FB1[index1]["S"]:
                                dprint("Case1")
                                FB1.insert(0, FB2[index2])
                                del FB2[index2]
                                total2 = len(FB2)
                                continue
                            
                            # SPECIAL Case 6 (Handle at the end of the while)
                            if FB1[index1]["E"] < FB2[index2]["S"]:
                                dprint("Case6")
                                index2 += 1
                                continue

                            # Case 2 (replace T1 start with T2, Delete T2)
                            if (FB2[index2]["S"] <= FB1[index1]["S"] and
                                FB2[index2]["E"] <= FB1[index1]["E"]):
                                dprint("Case2")
                                FB1[index1]["S"] = FB2[index2]["S"]
                                del FB2[index2]
                                total2 = len(FB2)
                                continue

                            # Case 3 (Replace T1 with T2)
                            if (FB2[index2]["S"] <= FB1[index1]["S"] and
                                FB1[index2]["E"] <= FB2[index1]["E"]):
                                dprint("Case3")
                                FB1[index1] = FB2[index2]
                                del FB2[index2]
                                total2 = len(FB2)
                                continue

                            # Case 4 (Delete T2, T1 encapsulates it)
                            if (FB1[index1]["S"] <= FB2[index2]["S"] and
                                FB2[index2]["E"] <= FB1[index1]["E"]):
                                dprint("Case4")
                                del FB2[index2]
                                total2 = len(FB2)
                                continue

                            # Case 5 (T1 ends before T2 end)
                            if (FB1[index1]["S"] <= FB2[index2]["S"] and
                                FB1[index1]["E"] <= FB2[index2]["E"] and
                                FB1[index1]["E"] <= FB2[index2]["S"]):
                                dprint("Case5")
                                FB1[index1]["E"] = FB2[index2]["E"]
                                del FB2[index2]
                                total2 = len(FB2)
                                continue

                        # End While index2
                        
                        index2 = 0
                        index1 += 1
                    # End While index1
                    
                    #Cover case 6
                    while total2 > 0:
                        FB1.append(FB2[0])
                        del FB2[0]
                        total2 = len(FB2)

                # End If Days Match
            # End Day 2
        # End Day 1

        dprint("Dumping merged schedules\nSchedule 1")
        dprint(schedule1)
        dprint("Schedule 2")
        dprint(schedule2)
        return schedule1
                            

    def flipSchedule(self, schedule, bt, et):
        dprint("Flipping Schedules")
        dprint(schedule)

        for day in schedule:
            times = []
            index = 0
            FB = day["FreeBusy"]

            FBLength = len(FB)
            if FBLength == 0:
                day["FreeBusy"] = [{"S" : bt, "E" : et}]
                continue

            if FB[0]["S"] < bt and bt < FB[0]["E"]:
                times.append(FB[0]["E"])
            else:
                times.append(bt)
                times.append(FB[0]["S"])
                times.append(FB[0]["E"])
                if FBLength == 1 and FB[0]["E"] < et:
                    times.append(et)

            for i in range(1, len(FB)):
                if et < FB[i]["E"]:
                    times.append(FB[i]["S"])
                    break
                if i == len(FB) - 1:
                    times.append(FB[i]["S"])
                    times.append(FB[i]["E"])
                    times.append(et)
                    break
                times.append(FB[i]["S"])
                times.append(FB[i]["E"])
            # End Looop

            # Sanity check loop
            for i in range(1, len(times)):
                if times[i-1] > times[i]:
                    print("PARSINGERROR")
                    print(day["Day"])
                    print(times)
                    print(FB)
                    raise

            newFB = []
            # Load Times into FreeBusy
            for i in range(1, len(times), 2):
                newFB.append({ "S" : times[i-1], "E" : times[i]})

            day["FreeBusy"] = newFB

        dprint("Free times")
        dprint(schedule)
        return schedule