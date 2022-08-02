from teamboard_requests import DashboardConnector

#TODO: change this according to your respective dashboard!
login_data = "username":"username", 
              "password":"password"}
              
def write_data(data, user_id):
    with open('outputfile.csv','w') as outlog:
        outlog.write('"Task Type";"Subject";"Content"\n')
        for d in data:
            if d['uuidOfCreator'] == user_id:
                ttype = "Problem"
                if 'task' in d['category']:
                    ttype = "Maßnahme"
                outlog.write('"{}";"{}";"{}"\n'.format(ttype, d['subject'], d['body']))
                try:
                    cause = d["taskProperties"]["problemDefinition"]
                    outlog.write('"{}";"{}";"{}"\n'.format("Ursache", d['subject'], cause))
                except KeyError:
                    continue  
                            

#Test fetching data:
connector = TeamboardConnector()
connector.set_url_real()
connector.set_login(login_data_real)
connector.init_connector()
connector.set_group("Key User")
#udata = connector.get_user_data()
all_data = connector.get_tasks()
#random hash for example id
texprax_account_creator_id = '50e3f43f-4f0c-4517-80d6-5df6818266e2'

write_data(all_data, texprax_account_creator_id)
