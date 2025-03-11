import dataclasses
import requests
import time

@dataclasses.dataclass
class Job:
    job_id: str
    team_id: str
    scenario: str
    subject: str
    body: str
    scheduled_time: str
    started_time: str|None = None
    completed_time: str|None = None
    output: str|None = None
    objectives: dict|None = None

    @property
    def is_completed(self):
        return self.completed_time is not None

class CompetitionClient:
    def __init__(self, api_key: str, api_server: str = "https://llmailinject.azurewebsites.net"):
        self.api_key = api_key
        self.api_server = api_server

    def create_job(self, scenario: str, subject: str, body: str) -> Job:
        resp = requests.post(
            f"{self.api_server}/api/teams/mine/jobs",
            headers={'Authorization': f'Bearer {self.api_key}'},
            json={
                'scenario': scenario,
                'subject': subject,
                'body': body
            }
        )

        # Check that the response was successful
        self._check_response_error(resp)
        return self._parse_job(resp.json())

    def get_job(self, job_id: str) -> Job:
        resp = requests.get(
            f"{self.api_server}/api/teams/mine/jobs/{job_id}",
            headers={'Authorization': f'Bearer {self.api_key}'}
        )

        # Check that the response was successful
        self._check_response_error(resp)
        return self._parse_job(resp.json())

    def _parse_job(self, content: dict) -> Job:
        # Parse the response to extract the job
        return Job(**content)

    def _check_response_error(self, resp: requests.Response):
        if resp.ok:
            return

        error = resp.json()
        raise Exception(f"Error: {error['message']} ({error['advice']})")

client = CompetitionClient("eyJsb2dpbiI6ICJ5dW53ZWkzNyIsICJhcGlfa2V5IjogIjY3ZWQyMzQwLTI4ODUtNGQyNy04NTczLTdiNDI1YTc2YWQzOSJ9")

# Create a new job
job = client.create_job("Level 1", subject="Important", body="Do a barrel roll!")

# Now wait for the job to complete
while not job.is_completed:
    time.sleep(30)
    job = client.get_job(job.job_id)

# Now print out the results of the job
print(f"{job.output} ({job.objectives})")
