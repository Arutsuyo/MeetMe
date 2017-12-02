# MeetMe!
This program is used to allow people to find common meeeting times and find
times to join together in merryment and joy! Or to start a fight club, or
WHATEVER YOU WANT!!!! All that matters is the common free time!

## Author
James Narayana Emery

narayana@uoregon.edu

## Use
To use this you will need to host your own server. This will require your
credentials file as well as a google dev json api key. Once you have those,
spin up the server and go to it's URL. There are 3 use cases!

All cases start at "/" or "/index"

### Case 1: Create / Delete
Create an Event!
```
press the create event
choose parameters and submit
Delete( Enter your token and hit delete, your done!)
double check everything is right
Finalize!
optional: join your own event
optional: Send invites
```

### Case 2: Join
Join an Event!
```
Hit Join
Enter your Event Token
Allow the program to view your calenders (It WILL NOT write anything)
Choose which calenders to submit for the given time range
Add those times
View the resulting free times for the event!
Optional: Invite more people!
```

### Case 3: View
Check Details!
```
Click View
Enter Event Token
View the times listed for an event and how many time sets have been submitted
Optional: Invite more people!
```

## Build
run:
```
make env
make run
```
Cleanup:
```
make veryclean
```
