from flask import Flask
import requests
import atexit
import time
from flask import render_template
#https://stackoverflow.com/questions/21214270/how-to-schedule-a-function-to-run-every-hour-on-flask
from apscheduler.schedulers.background import BackgroundScheduler 
import pickle
import json
from math import sqrt
import asyncio
from aiohttp import ClientSession


with open('./query_string.txt') as f:
    query_string = f.read()



app = Flask(__name__)


API_URLS = {
    'questions_list': "https://leetcode.com/api/problems/algorithms/",
    'question_info': 'http://leetcode.com/graphql',
}

def print_date_time():
    print(time.strftime("%A, %d. %B %Y %I:%M:%S %p"))

def make_query(query, variables, url):
    """
    Make query response
    """
    request = requests.post(url, json={'query': query, 'variables': variables})
    if request.status_code == 200:
        return request.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(
            request.status_code, query))



class Question:
    def __init__(self, q_id, name, difficulty, submissions, likes, dislikes, slug, stats):
        self.q_id = q_id
        self.name = name
        self.difficulty = difficulty
        self.submissions = submissions
        self.likes = likes
        self.dislikes = dislikes
        self.ratio = Question.calculate_like_dislike_ratio(likes, dislikes)
        self.slug = slug
        self.stats = stats

    @staticmethod
    def calculate_like_dislike_ratio(likes, dislikes):
        return likes / max(dislikes, 1)

    #https://stackoverflow.com/questions/10029588/python-implementation-of-the-wilson-score-interval
    #based on https://www.evanmiller.org/how-not-to-sort-by-average-rating.html
    def get_rating(self):
        n = self.likes + self.dislikes
        if n == 0:
            return 0
        z = 1.0 #1.44 = 85%, 1.96 = 95%
        phat = float(self.likes) / n
        return ((phat + z*z/(2*n) - z * sqrt((phat*(1-phat)+z*z/(4*n))/n))/(1+z*z/n))

    #for sorting
    def __lt__(self, other):
         return self.get_rating() < other.get_rating()

    def __str__(self):
        return f'Question {self.q_id}: {self.name} with a ratio of likes/dislikes {self.ratio:.2f}'

saved_questions = []
def read_saved_results():
    global saved_questions
    with open('./saved_results.pkl', 'rb') as f:
            saved_questions = pickle.load(f)

# @app.route('/')
# def home():
#     return 'LeetCode most liked questions'

@app.route('/')
def get_most_liked():
    return render_template('index.html', questions=saved_questions)

@app.route('/results')
def get_results():
    return json.dumps(saved_questions, default=lambda x: x.__dict__)

async def fetch(url, session, variables, query):
    async with session.post(url, json={'query': query, 'variables': variables}) as response:
        result = await response.read()
        return (result, variables['titleSlug']) #will use titleSlug for mapping back to questions in proper order


async def run(query_string, list_variables, url):
    tasks = []

    # Fetch all responses within one Client session,
    # keep connection alive for all requests.
    async with ClientSession() as session:
        for i in range(len(list_variables)):
            variables = list_variables[i]
            task = asyncio.ensure_future(fetch(url, session, variables=variables, query=query_string))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)
        # you now have all response bodies in this variable
        # print(responses[-1])
        return responses

def save_most_liked(top_k=-1):
    print('=' * 50)
    print("Starting a new fetch cycle for updating stored results...")
    print_date_time()

    response = requests.get(API_URLS['questions_list'])

    if not response.ok:
        print('Some error occured')

    json_response = response.json()
    list_of_questions = json_response['stat_status_pairs']

    map_slug_to_question_info = {}
    if top_k == -1:
        top_k = len(list_of_questions)
    
    list_variables = []

    for question in list_of_questions[:top_k]:
        stat_info = question['stat']
        if question['paid_only']:
            print(f"Skipping paid only question {stat_info['question_id']}...")
            continue
        title_slug = stat_info['question__title_slug']
        map_slug_to_question_info[title_slug] = question
        list_variables.append({"titleSlug": title_slug})
    
    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(run(query_string, list_variables, API_URLS['question_info']))
    responses = map(lambda x: (json.loads(x[0]), x[1]), loop.run_until_complete(future))

    questions = []

    #NOTE: careful here! responses are obviously not in the same order as they were async evaluated
    for response, title_slug in responses:
        question = map_slug_to_question_info[title_slug]
        difficulty_info = question['difficulty']
        stat_info = question['stat']
        result = response['data']['question']
        q = Question(q_id=stat_info['question_id'], difficulty=difficulty_info['level'], name=stat_info['question__title'],
                     submissions=stat_info['total_submitted'], likes=result['likes'], dislikes=result['dislikes'], slug=result['titleSlug'],
                     stats=json.loads(result['stats']))
        questions.append(q)


    print(f"Got {len(questions)} questions...")
    print("Sorting...")
    questions.sort(reverse=True)
    print("Printing fetched questions...")

    for q in questions:
        print(q)
        print(q.slug)

    print("Saving to file...")
    with open('./saved_results.pkl', 'wb') as f:
        pickle.dump(questions, f)
    print('=' * 50)


    global saved_questions
    read_saved_results() #update the global variable questions



EVERY_N_HOUR = 5

scheduler = BackgroundScheduler()
scheduler.add_job(func=save_most_liked, trigger="interval", minutes=EVERY_N_HOUR * 60)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown()) #close on shutdown

read_saved_results()
# save_most_liked() #call this for fetching all questions

# if __name__ == '__main__':
#     read_saved_results()
#     app.run(port=1337)
