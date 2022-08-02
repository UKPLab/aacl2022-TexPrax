import requests
import json
import time

#TODO: change this according to your respective dashboard!
login_data = "username":"username", 
              "password":"password"}
              
class DashboardConnector:

    def __init__(self):
        self.base_url = "targeturl" #TODO: set the correct target url!

    def init_connector(self):
        self.headers = {'Content-Type': 'application/json',
                        'accept': 'application/json; charset=UTF-8'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        # Set access token
        self.token = self.get_session_token()['token']
        self.session.headers.update({'Authorization': 'Bearer {}'.format(self.token)})
        # Set user data
        self.uuid = self.set_uuid()
        self.user_data = self.get_user_data()
        # Set a group
        self.group = {}
        
    def set_login(self, login_data):
        self.login_data = login_data
        self.auth_url = self.base_url + "/auth/jwt/authenticate"
        
    def get_session_token(self):
        response = requests.post(self.auth_url, 
                                 data = json.dumps(self.login_data),
                                 headers = self.headers)
        return response.json()
        
    def get_url(self, url):
        return self.base_url + url

    def get_user_data(self):
        response = self.session.get(self.get_url("/aaa/users/me"))
        return response.json()
        
    def get_timestamp(self):    
        # Fetch timestamp and add precision for milliseconds 
        return int(time.time()*1000)
        
    def get_tasks(self):
        # Fetch list of tasks bound to the current group id (Problemlösung)
        payload = {"activeOnly":True,
                   "categories":["problem"],
                   "firstResult":0,
                   "queryTotalCount":True,
                   "resolveRelations":True,
                   "taskProperties":{},
                   "uuidOfAssignedGroup":self.group["uuid"]}
        response = self.session.get(self.get_url("/projects/local.teamboard/tasks2"), 
                                 data = json.dumps(payload),
                                 headers = self.headers)
        return response.json()
        
    def filter_tasks(self,subject_text):
        # Select a list of tasks according to the subject (Titel) text
        # Sorted by last created first.
        result = []
        for task in self.get_tasks():
            if task["subject"] is not None:
                if task["subject"] in subject_text.strip():
                    result.append(task)
        return result
        
    def add_cause(self,subject_text, causetext):
        tasks = self.filter_tasks(subject_text)
        try:
            mod_task = tasks[0]
            mod_task["taskProperties"]["problemDefinition"] = causetext
            response = self.session.put(self.get_url("/projects/local.teamboard/tasks2?resolveAAA=true"), data = json.dumps([mod_task]))
        except (IndexError,KeyError) as e:
            return "Could not find task."
            
    def add_solution(self,subject_text, solution):
        # First, create the solution
        task_id = self.filter_tasks(subject_text)[0]["uuid"]
        solution_dict = {
            "category":"containment_task",
            "taskState":"CREATED",
            "timeOfCreation":self.get_timestamp(),
            "timeFinishedPlanned":self.get_timestamp(),
            "uuidOfCreator":self.uuid,
            "creator":self.user_data,
            "links":{"task:{}".format(task_id):"problem"},
            "taskProperties":{"customProperties":"{\"betroffenesKomponente\":{\"value\":null,\"secondTierValue\":null},\"variante\":{\"value\":null}}"},
            "uuidOfAssignedGroup":self.group['uuid'],
            "uuidOfAssignedUser":self.uuid,
            "subject":"Maßnahme: {}".format(subject_text),
            "body":solution,
            "archived":False,
            "timeFinishedActual":None,
            }
        response_solution = self.session.put(self.get_url("/projects/local.teamboard/tasks2?resolveAAA=true"), data = json.dumps([solution_dict])).json()[0]

        # Then update the problem with a link to the new solution
        solution_id = response_solution["uuid"]
        problem_dict = self.get_task_dict(task_id)
        problem_dict["links"] = {"task:{}".format(solution_id):"containment_task"}

        self.session.put(self.get_url("/projects/local.teamboard/tasks2?resolveAAA=true"), data = json.dumps([problem_dict]))
         
    def set_uuid(self):
        response = self.session.get(self.get_url("/auth/whoami"))
        return response.json()['uuid']

    def set_group(self, groupname):
        response = self.session.get(self.get_url("/aaa/groups"))
        responses = response.json()
        for group in responses:
            if group['label'] == groupname:
                self.group = group
                print("Group found. Setting {}".format(groupname))
                break
                
        # If a group cannot be found, set the first group as the default one
        if not self.group:
            print("Group not found. Setting {}".format(responses[0]['label']))
            self.group = responses[0]
        
    def create_problem(self, problem_text, description=None):
        # Create a simple problem
        subject_text = problem_text[:75] if len(problem_text) >= 75 else problem_text
        problem_dict = {
            "category":"problem",
            "taskState":"CREATED",
            "timeOfCreation":self.get_timestamp(),
            "timeFinishedPlanned":self.get_timestamp(),
            "uuidOfCreator":self.uuid,
            "creator":self.user_data,
            "taskProperties":{
                "problemsolvingType":"1",
                "hasPDCA":"true",
                "pdcaState":"0",
                "ishikawa":"{\"name\":\"Problem\",\"children\":[{\"name\":\"Maschine\",\"children\":[]},{\"name\":\"Methode\",\"children\":[]},{\"name\":\"Material\",\"children\":[]},{\"name\":\"Mensch\",\"children\":[]},{\"name\":\"Umwelt\",\"children\":[]}]}",
            "customProperties":"{\"betroffenesKomponente\":{\"value\":null,\"secondTierValue\":null},\"variante\":{\"value\":null}}"
            },
            "uuidOfAssignedGroup":self.group['uuid'],
            "uuidOfAssignedUser":self.uuid,
            "subject":subject_text,
            "body": description if description is not None else problem_text,
            "archived":False,
            "timeFinishedActual":None,
            }
        
        response = self.session.put(self.get_url("/projects/local.teamboard/tasks2?resolveAAA=true"), data=json.dumps([problem_dict]))

    def get_task_dict(self, uuid):        
        tasks = self.get_tasks()
        for t in tasks:
            if t["uuid"] == uuid:
                return t
        return {}


if __name__ == "__main__":
    # Example usage:
    connector = DashboardConnector()
    connector.set_login(login_data)
    connector.init_connector()
    connector.set_group("Key User")
    connector.create_problem("Neustes Beispielproblem 1")
    connector.add_cause("Neustes Beispielproblem 1", "Beispielursache")
    connector.add_solution("Neustes Beispielproblem 1", "Das ist eine Beispielmassnahme")



