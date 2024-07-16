import socket
import math
import subprocess
import xml.etree.ElementTree as ET
# To be modified ********************************************

##mainDirectory='NameOfYourDirectory'
##RoleToRdp={
##       'R1':{'rdp_nc':'unconstrainedPetriNetNameR1', 'rdp_c':'constrainedPetriNetNameR1'}, #Role 1: write the Petri Net files names (no extension)
##       'R2':{'rdp_nc':'unconstrainedPetriNetNameR2', 'rdp_c':'constrainedPetriNetNameR2'} #Role 2. If you have other roles, add other lines.
##}
##TCscenarios = [
##       [{"R1":'1stCommonTaskforR1', "R2":'1stCommonTaskforR2'}, {"R1":'2ndCommonTaskforR1', "R2":'2ndCommonTaskforR2'}], #each list transcribes a sequence of common tasks in the order of execution. If multiple sequences are possible, add each of them in a separate list.
##]

#EXAMPLE TEST **************************** Comment this section if you want to analyse your own scenario

mainDirectory='V1.4_lycee'
RoleToRdp={
       'R1':{'rdp_nc':'XPlycee_v4.1_R1', 'rdp_c':'XPlycee_v4.1_R1_long'},
       'R2':{'rdp_nc':'XPlycee_v4.1_R2', 'rdp_c':'XPlycee_v4.1_R2_long'}
}
TCscenarios = [
       [{"R1":'do B', "R2":'do K'}, {"R1":'do H', "R2":'do L'}, {"R1":'do T', "R2":'do V'}],
]

#End modifications ************************************************
fullPetriNetsPath = "./"+mainDirectory+"/fullPetriNets" # contains Petri nets with all actions available
filteredPetriNetsPath = "./"+mainDirectory+"/filteredPetriNets" # contains Petri nets with actions selected by experts
featuresPath = "./"+mainDirectory+"/specifications" # define for each action if it is a player/system action and if it is an end action

actionsMetaData = {}

# Definitions:

# Send a request to Laalys and return result
def sendRequest(keyword, options):
    request = keyword
    for opt in options:
            request = request+ "\t" + str(opt)
    #print ("Send request: "+request)
    client.send(request.encode())
    #print ("Waiting answer...")
    msg = client.recv(2048)
    response = msg.decode()
    while len(msg) == 2048:
            msg = client.recv(2048)
            response = response + msg.decode()
    return response[:-2] #remove the last \r\n

# Loads network specifications "rdpName" if not already loaded
def loadPnMetaData (rdpName):
    global actionsMetaData
    if rdpName not in actionsMetaData:
        actionsMetaData[rdpName] = {}
        tree = ET.parse(featuresPath+"/"+str(rdpName)+'.xml')
        root = tree.getroot()
        for transition in root.findall('transition'):
            actionsMetaData[rdpName][transition.get('id')] = {
                "system": transition.get('system') == 'true',
                "noTimeAction": True if transition.get('noTimeAction') == 'true' else False,
                "mandatory": transition.get('mandatory') == 'true'
            }

#check if it is a system action
def isSystem(action, rdpName):
    global actionsMetaData
    loadPnMetaData (rdpName)
    return actionsMetaData[rdpName][action]["system"]

#check if this is a mandatory action (system actions are mandatory by default)    
def isMandatory(action, rdpName):
    global actionsMetaData
    loadPnMetaData (rdpName)
    return actionsMetaData[rdpName][action]["mandatory"]

#check if this is a mandatory action (system actions are mandatory by default)   
def isNoTime(action, rdpName):
    global actionsMetaData
    loadPnMetaData (rdpName)
    return actionsMetaData[rdpName][action]["noTimeAction"]

def getTime(action, rdpName):
    global actionsMetaData
    loadPnMetaData (rdpName)
    return 0 if isSystem(action, rdpName) or isNoTime(action, rdpName) else 1
    #return actionsMetaData[rdpName][action]["time"]

# execute the actions and returns the time consumed by executing these actions
def execActions(listOfActions, rdpName):
    time = 0
    for step in listOfActions:
        performedBy = "system" if isSystem(step, rdpName) else "player"
        time += getTime(step, rdpName)
        sendRequest(rdpName, [step, performedBy])
    return time

# sorts the action list from longest to shortest
#def sortActionByTime (actions, rdpName)
#    timedActions = []
#    for action in actions:
#        timedActions = timedActions+[(action, getTime(step, rdpName))]
#    # sort the list of actions by their time (from longest to shortest) and return only the first component from this sorted list
#    return [paire[0] for paire in sorted(timedActions, key=lambda x: x[1], reverse=True)]

# calculates the time to reach the action "target" in the rdp "rdpName". "strategy" can contain the value 'long' or 'short' and is indicated if we seek to maximize or minimize the time.
def computeTime (rdpName, target, strategy):
    global nbActionMax
    
    # Save current marking
    currentMarking = sendRequest("GetPetriNetsMarkings", [rdpName])
    response = sendRequest("NextActionToReach", [rdpName, target, nbActionMax])
    if response == "" or response.startswith("Error, Exception"):
        raise Exception("Unreachable", target+" is not an achievable task in "+rdpName)
    
    time = 0
    # Divide each path into tasks
    tasks = response.split('\t')
    # Count and execute all tasks except the last one (the target)
    time += execActions(tasks[:-1], rdpName)
    # If the strategy is to maximize the time before executing target, we execute all active tasks
    if strategy=='long':
        # recovery of active actions
        triggerableActions = sendRequest("TriggerableActions", [rdpName]).split('\t')
        # As long as we have at least two tasks to execute including the target
        
        while target in triggerableActions and len(triggerableActions) > 1:
            triggerableActions.remove(target)
            prevMarking = sendRequest("GetPetriNetsMarkings", [rdpName])
            # execute the most time-consuming action
            time += execActions([triggerableActions[0]], rdpName)
            newMarking = sendRequest("GetPetriNetsMarkings", [rdpName])
            # Check that the marking has evolved to prevent infinite loops
            if prevMarking == newMarking:
                # Here we triggered an action which did not change the marking => we can run infinitely, so we set the time to the maximum value
                time = math.inf
                break
            
            # Retrieve new available actions
            triggerableActions = sendRequest("TriggerableActions", [rdpName]).split('\t')
        # Check that the target is still sensitized
        response = sendRequest("NextActionToReach", [rdpName, target, nbActionMax])
        if target not in triggerableActions and (response == "" or response.startswith("Error, Exception")):
            raise Exception("Unreachable", target+" is no longer reachable in "+rdpName)
        elif target not in triggerableActions and time<math.inf:
            time+=computeTime(rdpName, target, strategy)
    
    # Restore the marking save to cancel the simulation carried out
    sendRequest("SetPetriNetsMarkings", [currentMarking])
    return time
    

# Advances the network "rdp Name" until it reaches "TCR" and until the time limit "borne" is reached.
def progressToReachTC (rdpName, TCR, borne, mandatoryFirst): 
    global nbActionMax
    response = sendRequest("NextActionToReach", [rdpName, TCR, nbActionMax])
    if response == "" or response.startswith("Error, Exception"):
        raise Exception("Unreachable", target+" is not an achievable task in "+rdpName)
    
    # recovery of the list of tasks returned by Laalys
    tasks = response.split('\t')
    # Perform minimal actions
    i = execActions(tasks[:-1], rdpName)
    # Continue performing actions until you reach the "borne"
    while i < borne:
        # Get possible actions
        response2 = sendRequest("TriggerableActions", [rdpName])
        triggerableActions = response2.split('\t')
        
        # To avoid executing TCR, we remove it from the list of triggerable actions
        if TCR in triggerableActions:
            triggerableActions.remove(TCR)
        #print("Triggerable actions: ",triggerableActions)
        
        # Browse the possible actions to execute a mandatory task as a priority if you are in mandatoryFirst, or a non-mandatory task otherwise.
        executed = False
        for task in triggerableActions:
            # We execute a mandatory action if we are in mandatoryFirst mode
            # OR we execute a non-mandatory action if we are in non-mandatory mode
            if (mandatoryFirst and isMandatory(task,rdpName)) or (mandatoryFirst==False and isMandatory(task,rdpName)==False):
                i+=execActions([task], rdpName)
                executed = True # Note that an action has been performed
                break
        # If we have not executed an action, we execute the first come
        if executed==False:
            i+=execActions([triggerableActions[0]], rdpName)

    response = sendRequest("NextActionToReach", [rdpName, TCR, nbActionMax])   
    if response == "" or response.startswith("Error, Exception"):
        raise Exception("Unreachable", TCR+" is no longer reachable in "+rdpName)
    else:
        i+=execActions(response.split("\t")[:-1], rdpName)
    return i

# This function calculates the overlap distance by calculating the minimum distance between the min of each role and the max of the other roles
def overlapDistance(mins, maxs):
    distMin = None
    i_min = 0
    while i_min < len(mins):
        i_max = 0
        while i_max < len(maxs):
            if i_min != i_max: # To avoid calculating the distance with yourself
                dist = maxs[i_max] - mins[i_min]
                if distMin == None or dist < distMin:
                     distMin = dist
            i_max += 1
        i_min += 1
    return distMin

print ("Launch server")
socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
socket.bind(('127.0.0.1', 12012))
print ("Launch Laalys")
graphType = "ACCESS" # If ACCESS compute Accessible graph, if COVER compute coverability graph
# Launch Laalys jar file
subprocess.Popen(["java.exe", "-jar", "./LaalysV2.jar", "-fullPn", fullPetriNetsPath, "-filteredPn", filteredPetriNetsPath, "-features", featuresPath, "-serverIP", "localhost", "-serverPort", "12012", "-kind", graphType])
print ("Waiting Laalys connexion")
socket.listen()
client, address = socket.accept()
print ("Laalys connected")
print ("")


#variables
borne1=0
borne2=0
global nbActionMax
nbActionMax=100
risk=0
common=0

# Get the initial marking of all rdp
initialMarkings = sendRequest("GetPetriNetsMarkings", [])

#browse all scenarios
for TCscenario in TCscenarios:
    print("\nAnalysis of a new scenario")
    cumulTime={}   
    historiqueBornes=[]
    #reposition all networks in their initial marking
    sendRequest("SetPetriNetsMarkings", [initialMarkings])
    # be careful to recalculate the accessibility graphs of the constrained networks in case they have been modified for a previous scenario
    for role,rdps in RoleToRdp.items():
        sendRequest("ResetPetriNetsFromCurrentMarkings", [rdps["rdp_c"]])
        
    #go through all the TCs in the scenario
    for TC in TCscenario:
        common=common+1
        print("\nAnalysis of the common task concerning: ", TC)
        
        # initialize the cumulTime the first time we encounter this role
        for role, tache in TC.items():  
            if role not in cumulTime:
                cumulTime[role] = {"min":0,"max":0}
        
        # We start by calculating the time window which encompasses the TCs of the roles involved
        # To do this, we will record in two lists the minimum and maximum times of the different roles involved in carrying out the common task.
        # We therefore create two lists to store these times
        mins = []
        maxs = []
        # We go through all the roles involved in this common task
        for role, tache in TC.items():    
            # Get the RdP of the targeted role
            rdpName_nc = RoleToRdp[role]["rdp_nc"]
            rdpName_c = RoleToRdp[role]["rdp_c"]
            # Recording the minimum time taking into account the minimum history accumulated for this role and the calculation of the minimum time required to reach the task in the unconstrained RdP
            mins.append(cumulTime[role]["min"]+computeTime (rdpName_nc, tache, 'short'))
            # Recording the maximum time taking into account the maximum history accumulated for this role and the calculation of the maximum time required to reach the task in the constrained RdP
            maxs.append(cumulTime[role]["max"]+computeTime (rdpName_c, tache, 'long'))
            
            if mins[len(mins)-1]== maxs[len(maxs)-1]:
                print(role,"'",tache,"'","is accessible after ", mins[len(mins)-1]," TU")
            if mins[len(mins)-1]< maxs[len(maxs)-1]:
                print(role,"'",tache,"'","is accessible after ", mins[len(mins)-1]," to ",maxs[len(maxs)-1]," TU")
        
        # We now have in the two lists mins and maxs the minimum and maximum times for the different roles to carry out the common task
        overlapDist = overlapDistance(mins, maxs)

        # "Bornes" analysis 
        # Case where there is a serious problem => no overlap
        if overlapDist < 0:
            risk=risk+100
            print("/!\ Overlap error, analysis stopped.")
            historiqueBornes.append("Concerning "+str(TC)+": INTERRUPTED ANALYSIS DUE TO OVERLAP ERROR. Please correct the error below and try again => The tasks can't be performed at the same time. There is "+str(abs(overlapDist))+" TU difference between the roles to access these tasks. Add other (side) task(s) of at least "+str(abs(overlapDist))+" TU to make up this difference.")
            break
        else:
            # Case where the overlap is reasonable (distance of 2 or more therefore overlap of 3 TU or more)
            if overlapDist >= 2:
                historiqueBornes.append("Concerning "+str(TC)+": Overlapping ok, these common tasks will be accessible over a "+str(overlapDist)+"-TU time windows.")
            # Case where there is a low overlap (distance of 1 therefore an overlap of 2 TU => risky)
            elif overlapDist >= 1:
                risk=risk+1
                historiqueBornes.append("Concerning "+str(TC)+": The allocated time for interaction between roles is a bit tight. We recommend adding one or two side tasks before the common tasks to avoid waiting times if a player is faster or slower than expected.")
            # Case where the overlap is only 1 TU => very risky
            else:
                risk=risk+2
                historiqueBornes.append("Concerning "+str(TC)+": Overlap WARNING. The common tasks will be accessible on only one TU => There is no margin of time to complete common tasks. If the estimated duration does not correspond to reality, a role may be waiting for another one. We suggest you to add some side tasks to compensate for differences in speed between players.")                

            # To calculate the new starting points for each role we retain the maximum of the minimums and the minimum of the maximums
            borne1 = max(mins)
            borne2 = min(maxs)

            # Now that we have identified the overlap window, we must move the different networks forward accordingly.
            # We go through all the roles involved in this common task
            for role, tache in TC.items():    
                # Get the current role RdP 
                rdpName_nc = RoleToRdp[role]["rdp_nc"]
                rdpName_c = RoleToRdp[role]["rdp_c"]
                
                # We save the marking of the unconstrained RdP
                saveMarking = sendRequest("GetPetriNetsMarkings", [rdpName_nc])

                # for the maximum of this window we generate the state of the unconstrained network to reach the common task by favoring the mandatory tasks until the common task is available then then prioritizing the optional ones
                dt = borne2-cumulTime[role]["max"]
                timeElapsed=progressToReachTC (rdpName_nc, tache, dt, False)
                cumulTime[role]["max"] = borne2 + timeElapsed - dt
                # We save the marking
                newMarkingNC_Long = sendRequest("GetPetriNetsMarkings", [rdpName_nc])
                # We force the CONSTRAINED rdp into the UNCONSTRAINED marking state in which we played the long scenario (prioritization of optional tasks) => Be careful with the name change
                newMarkingLong_withoutName = '\t'.join(newMarkingNC_Long.split('\t')[1:])
                sendRequest("SetPetriNetsMarkings", [rdpName_c, newMarkingLong_withoutName])
                # By forcing the marking we can position the constrained RdP in a state which may not exist in its accessibility graph, we therefore ask Laalys to recalculate the accessibility graphs of the constrained RdP
                sendRequest("ResetPetriNetsFromCurrentMarkings", [rdpName_c])

                # Return the unconstrained RdP to its saved state to play the short scenario
                sendRequest("SetPetriNetsMarkings", [saveMarking])
                
                # for the min of this window we generate the state of the unconstrained network to achieve the common task by favoring the mandatory tasks
                dt = borne1-cumulTime[role]["min"]
                timeElapsed=progressToReachTC (rdpName_nc, tache, dt, True)
                cumulTime[role]["min"] = borne1 + timeElapsed - dt
            
    # Viewing the analysis
    print("\nAnalysis summary:")
    for hist in historiqueBornes:
         print('\t'+hist)
    print()
    print("The scenario contains "+str(common)+" common tasks and your risk score is: "+str(risk)+". If your score is close to 0, you maximize the players' chances to cooperate simultaneously. If your score is 100 or higher, it means that there is at least one common task that cannot be completed synchronously. Waiting for one role can affect the scenarios of all roles and cause problems for all other common tasks as a result.")
    if risk >= 100:
            print("The scenario poses major problems of synchronicity. Follow the tips above to ensure players will be able to complete common tasks simultaneously.")
    elif risk > common:
            print("In your situation, there is a big risk that players will not be able to cooperate at the planned times. Read the advice given above to reduce the risks.")
    elif risk <= common and risk >2:
            print("In your situation, improvements are recommended, but it is nevertheless possible that everything will go according to plan if the players are on time.")
    elif risk <2 and risk >0:
            print("In your situation, small improvements can be made but there should be no problem getting players to meet at the right times.")
    elif risk ==0:
            print("In your situation, you have created enough side tasks, the roles should not have difficulty carrying out common tasks simultaneously.")


    print("End of analysis of this scenario")
    risk=0



#Close connection with Laalys
client.send("Quit".encode())
client.close()
socket.close()
