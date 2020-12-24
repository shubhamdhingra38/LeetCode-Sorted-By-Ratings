from flask import Flask
import requests
import atexit
import time
#https://stackoverflow.com/questions/21214270/how-to-schedule-a-function-to-run-every-hour-on-flask
from apscheduler.schedulers.background import BackgroundScheduler 
import pickle


with open('./query_string.txt') as f:
    query_string = f.read()

app = Flask(__name__)


API_URLS = {
    'questions_list': "https://leetcode.com/api/problems/algorithms/",
    'question_info': 'https://leetcode.com/graphql',
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
from math import sqrt



class Question:
    def __init__(self, q_id, name, difficulty, submissions, likes, dislikes):
        self.q_id = q_id
        self.name = name
        self.difficulty = difficulty
        self.submissions = submissions
        self.likes = likes
        self.dislikes = dislikes
        self.ratio = Question.calculate_like_dislike_ratio(likes, dislikes)

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
        return f'Question {self.q_id}: {self.name} with a ratio of likes/dislikes {self.ratio}'


@app.route('/')
def home():
    return 'LeetCode most liked questions'


@app.route('/most-liked/<int:top_k>')
def get_most_liked(top_k):
    with open('./saved_results.pkl', 'rb') as f:
        questions = pickle.load(f)
    results = []
    for q_idx in range(min(top_k, len(questions))):
        results.append(str(questions[q_idx]))
    return '\n'.join(results)

def save_most_liked(top_k=10):
    print('=' * 50)
    print("Starting a new fetch cycle for updating stored results...")
    print_date_time()
    response = requests.get(API_URLS['questions_list'])

    if not response.ok:
        print('Some error occured')

    json_response = response.json()
    list_of_questions = json_response['stat_status_pairs']
    questions = []

    for question in list_of_questions[:top_k]:
        difficulty_info = question['difficulty']
        stat_info = question['stat']
        if question['paid_only']:
            print(f"Skipping paid only question {stat_info['question_id']}...")
            continue

        try:
            result = make_query(query_string, variables={
                                "titleSlug": stat_info['question__title_slug']}, url=API_URLS['question_info'])
        except:
            print('Some error occured')
            continue
        result = result['data']['question']
        q = Question(q_id=stat_info['question_id'], difficulty=difficulty_info['level'], name=stat_info['question__title'],
                     submissions=stat_info['total_submitted'], likes=result['likes'], dislikes=result['dislikes'])
        questions.append(q)

    print(f"Got {len(questions)} questions...")
    print("Sorting...")
    questions.sort(reverse=True)
    print("Printing fetched questions...")
    for q in questions:
        print(q)
    print("Saving to file...")
    with open('saved_results.pkl', 'wb') as f:
        pickle.dump(questions, f)
    print('=' * 50)



scheduler = BackgroundScheduler()
scheduler.add_job(func=save_most_liked, trigger="interval", seconds=300)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown()) #close on shutdown



if __name__ == '__main__':
    app.run()