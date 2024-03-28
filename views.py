from flask import render_template, Blueprint, redirect, url_for, request, session, current_app as app
import requests
from CTFd.utils import config
from CTFd.utils import get_config
from CTFd.utils.decorators.visibility import check_score_visibility
from CTFd.models import Teams, Fields
from CTFd.schemas.teams import TeamSchema
from .scores import get_unmatched_standings, get_matched_standings, get_custom_standings


class CTFdUserCustomFieldChecker:
    def __init__(self, url):
        self.url = url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": "Token ctfd_68c5f71f55ae8191de8930fe2e2dd8a565b413e9f130f5eeccb091b1b4454988"
        })
        self.team_id_name_map = self.fetch_teams()
        self.military_count = 0
        self.civilian_count = 0
        self.other_count = 0
        self.military_team_count = 0
        self.civilian_team_count = 0
        self.other_team_count = 0
        self.users_with_issues_count = 0
        self.users_without_team = []
        self.users_with_field_issues = []
        self.military_teams = []
        self.civilian_teams = []
        self.other_teams = []
          
    def fetch_teams(self):
        team_id_name_map = {}
        page = 1
        while True:
            response = self.session.get(f"{self.url}/api/v1/teams?page={page}")
            if response.status_code == 200 and response.json().get("data"):
                for team in response.json().get("data"):
                    team_id_name_map[team['id']] = team['name']
                page += 1
                if not response.json().get("meta", {}).get("pagination", {}).get("next"):
                    break
            else:
                break
        return team_id_name_map


    def fetch_and_analyze_users(self):
        page = 1
        all_users_info = []
        while True:
            response = self.session.get(f"{self.url}/api/v1/users?page={page}")
            if response.status_code == 200 and response.json().get("data"):
                for element in response.json().get("data"):
                    user_info, has_issue = self.process_user(element)
                    all_users_info.append(user_info)
                    if has_issue:
                        self.users_with_issues_count += 1
                page += 1
            else:
                break
        return all_users_info
    
    def process_user(self, user_data):
        user_name = user_data.get("name")
        user_id = user_data.get("id")
        team_id = user_data.get("team_id")
        team_name = self.team_id_name_map.get(team_id, "") # No Team

        if not team_name or team_name == "": # No Team
            self.users_without_team.append({"user_name": user_name, "id": user_id})

        custom_fields = []
        for field in user_data.get("fields", []):
            if field.get("value") == True:
                if "Military" in field.get("name"):
                    custom_fields.append("Military")
                    self.military_count += 1
                elif "Civilian" in field.get("name"):
                    custom_fields.append("Civilian")
                    self.civilian_count += 1
                else:
                    custom_fields.append("Other")
                    self.other_count += 1

        has_issue = len(custom_fields) != 1
        if has_issue:
            self.users_with_field_issues.append({"user_name": user_name, "id": user_id, "custom_fields": ", ".join(custom_fields)})

        custom_fields_str = ", ".join(custom_fields) if custom_fields else "" # None
        return {"user_name": user_name, "id": user_id, "team": team_name, "custom_fields": custom_fields_str}, has_issue

    def fetch_num_teams(self):
            response = self.session.get(f"{self.url}/api/v1/statistics/teams")
            if response.status_code == 200 and response.json().get("data"):
                data = response.json().get("data")
                return data["registered"]
            return 0
    

    def fetch_team_scores(self):
        team_scores = {}
        response = self.session.get(f"{self.url}/api/v1/scoreboard")
        if response.status_code == 200:
            scoreboard_data = response.json().get('data', [])
            for team in scoreboard_data:
                team_id = team['account_id']
                score = team['score']
                team_scores[team_id] = score
        
        return team_scores
    

    def analyze_and_display_teams(self, team_user_counts):
            team_scores = self.fetch_team_scores()
            self.team_details = []
            self.teams_with_issues = []
            self.field_mismatch_attention = []
            self.team_sizes = {k: 0 for k in range(1, 6)}  
            
            for team_id, team_name in self.team_id_name_map.items():
                members_count = self.team_user_counts.get(team_id, 0)
                self.team_sizes[min(members_count, 5)] += 1  
                team_score = team_scores.get(team_id, 0)  
                
                response = self.session.get(f"{self.url}/api/v1/teams/{team_id}")
                if response.status_code == 200:
                    team_data = response.json().get("data")
                    
                    custom_fields = []
                    for field in team_data.get("fields", []):
                        if field.get("value") == True:
                            if "Military" in field.get("name"):
                                custom_fields.append("Military")
                                self.military_teams.append({"ID": team_id, 
                                "name": team_name, 
                                "Members": members_count, 
                                "account_id": team_id,
                                "score": team_score,
                                "oauth_id": None})
                                self.military_team_count += 1
                            elif "Civilian" in field.get("name"):
                                self.civilian_teams.append({"ID": team_id, 
                                "name": team_name, 
                                "Members": members_count, 
                                "account_id": team_id,
                                "score": team_score,
                                "oauth_id": None})
                                custom_fields.append("Civilian")
                                self.civilian_team_count += 1
                            else:
                                self.other_teams.append({
                                "ID": team_id, 
                                "name": team_name, 
                                "Members": members_count, 
                                "account_id": team_id,
                                "score": team_score,
                                "oauth_id": None
                                })
                                custom_fields.append("Other")
                                self.other_team_count += 1

                    custom_fields_str = ", ".join(custom_fields) if custom_fields else "" # No custom field
                    
                    self.team_details.append({
                        "ID": team_id, 
                        "Team Name": team_name, 
                        "Members": members_count, 
                        "Custom Fields": custom_fields_str,
                        "Score": team_score
                    })

                    has_issue = len(custom_fields) != 1
                    
                    if has_issue:
                        self.teams_with_issues.append({"team_name": team_name, "id": team_id, "custom_fields": ", ".join(custom_fields)})

    def fetch_team_members(self):
            self.team_user_counts = {}
            page = 1
            while True:
                response = self.session.get(f"{self.url}/api/v1/users?page={page}")
                if response.status_code == 200 and response.json().get("data"):
                    for user in response.json().get("data"):
                        team_id = user.get("team_id")
                        if team_id:
                            if team_id in self.team_user_counts:
                                self.team_user_counts[team_id] += 1
                            else:
                                self.team_user_counts[team_id] = 1
                    page += 1
                else:
                    break
            return self.team_user_counts


@app.route('/scoreboard', methods=['GET', 'POST'])
@check_score_visibility
def view_split_scoreboard():
    team_ids = session.get('teams_watching')
    if team_ids == None:
        team_ids = []
    if request.method == 'POST':
        team_ids = [int(e) for e in request.form.getlist('teams') if str(e).isdigit()]
        if(all(isinstance(item, int) for item in team_ids)):
            session['teams_watching'] = team_ids
    matched_standings = get_matched_standings()
    unmatched_standings = get_unmatched_standings()
    custom_standings = get_custom_standings(team_ids=team_ids)
    teams = Teams.query.filter_by(banned=False)
    watching = session.get('teams_watching')


    selected_value = get_config("split_scoreboard_value") if get_config("split_scoreboard_value") != None else 1
    selected_attr_id = get_config("split_scoreboard_attr") if get_config("split_scoreboard_attr") != None else -1
    selected_attr_matched_title = get_config("split_scoreboard_attr_matched_title") if get_config("split_scoreboard_attr_matched_title") != None else "matched"
    selected_attr_unmatched_title = get_config("split_scoreboard_attr_unmatched_title") if get_config("split_scoreboard_attr_unmatched_title") != None else "unmatched"

   
    if int(selected_attr_id) > 0:
        attr_name = Fields.query.filter_by(id=selected_attr_id).first_or_404()
        attr_name = attr_name.name
    elif int(selected_attr_id) == -1:
        attr_name = "Team Size is "+str(selected_value)
    elif int(selected_attr_id) == -2:
        attr_name = "Team Size is less than "+str(selected_value)
    elif int(selected_attr_id) == -3:
        attr_name = "Team Size is greater than "+str(selected_value)
	
    # Multiple scoreboards implementation for CSCTF starts here
    api_handler = CTFdUserCustomFieldChecker("http://127.0.0.1:8000")
    team_user_count = api_handler.fetch_team_members()
    api_handler.analyze_and_display_teams(team_user_count)
    api_handler.civilian_teams = sorted(api_handler.civilian_teams, key=lambda element: element["score"],reverse=True)
    api_handler.military_teams = sorted(api_handler.military_teams, key=lambda element: element["score"], reverse=True)
    api_handler.other_teams = sorted(api_handler.other_teams, key=lambda element: element["score"], reverse=True)


    show_custom = get_config("split_scoreboard_custom")
    return render_template(
       'scoreboard.html',
		custom = show_custom,
        teams = teams,
		matched_title = selected_attr_matched_title,
		unmatched_title = selected_attr_unmatched_title,
        watching = watching,
        matched_standings = api_handler.military_teams,
        unmatched_standings = api_handler.civilian_teams,
        matched_standings_2 = api_handler.other_teams,
        custom_standings = custom_standings,
        score_frozen=config.is_scoreboard_frozen()
    )
    

