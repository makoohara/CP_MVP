from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort
from . import db
import openai
from .models import History
from flask_cors import CORS
from flask_login import current_user, login_required
from datetime import datetime
import spacy
#import en_core_web_sm
from collections import Counter
from dotenv import load_dotenv
import os

load_dotenv()

main = Blueprint('main', __name__)
# app = Flask(__name__)

# Define OpenAI API key
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key set as environment variable")
openai.api_key = OPENAI_API_KEY

# Load the spaCy model
# nlp = spacy.load("en_core_web_sm")

nlp = spacy.load('/Users/oharamako/Library/Python/3.8/lib/python/site-packages/en_core_web_sm/en_core_web_sm-3.7.1')

# Enable CORS
# CORS(app)


def recommend_song(entry):

    # Building the OpenAI API prompt based on the request body
    prompt = f"Empathize this diary entry with a song: {entry} . Return the song title and artist only."

    # Adding genre information to the prompt if available
    genre = request.json.get('genre')
    if genre:
        prompt += f" Pick from the genre = '{genre}'"
    print(prompt)

    # Calling the OpenAI API to generate a song recommendation based on the prompt
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.4,
        max_tokens=64,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=["."]
    )

    # Building a new OpenAI API prompt based on the song recommendation
    print('song recommendation', response)
    song_title = response.choices[0].text.strip()
    prompt2 = f"What is the lyric part that resonates with {entry} in {song_title}? Respond in the form: lyrics from song by artist"
    print('lyrics prompt', prompt2)

    # Calling the OpenAI API to generate a response based on the new prompt
    response2 = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt2,
        temperature=0.4,
        max_tokens=64,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    # Logging the response generated by the second OpenAI API call
    response_text = response2.choices[0].text.strip()
    print('lyrics response', response_text)

    return response_text

def extract_keywords_spacy(text):
    # Process the text with spaCy
    doc = nlp(text)

    # Extract entities and nouns as keywords
    keywords = [token.text.lower() for token in doc if token.pos_ in ['NOUN', 'PROPN']]
    entities = [entity.text.lower() for entity in doc.ents]

    # Combine keywords and entities
    all_keywords = keywords + entities

    return all_keywords

def weight_keywords(keywords):
    # Simple weighting based on frequency
    weighted_keywords = Counter(keywords)
    return weighted_keywords

def create_image_prompt(weighted_keywords):
    # Constructing the prompt
    prompt_parts = [word for word, _ in weighted_keywords.most_common(3)]
    return 'Artistic style with a color scheme of ' + ', '.join(prompt_parts)

def create_prompt(entry):
    keywords = extract_keywords_spacy(entry)
    weighted_keywords = weight_keywords(keywords)
    prompt = create_image_prompt(weighted_keywords)
    print('Image generation prompt:', prompt)
    return prompt


def generate_image_url(prompt):
    # Use the GPT API to create a prompt designated for DALL-E
    dalle_prompt = prompt + ' ,artistic'
    print('final dalle prompt:', dalle_prompt)
    response = openai.Image.create(
        prompt=(dalle_prompt),
        n=1,
        size="256x256",
    )

    img_url = response["data"][0]["url"]
    print(img_url)
    return img_url


def app_main(request):
    try:
        data = {}
        print('main')
        entry = request.json.get('mood')
        data['song'] = recommend_song(entry)
        data['img_url'] = generate_image_url(create_prompt(entry))
        print(data)
        return data

    except Exception as e:
        # Handling errors by sending an error response
        return jsonify({'error': str(e)}), 500


@main.route('/', methods=['POST', 'GET'])
@login_required
def home():
    if request.method == 'POST':
        data = app_main(request)
        print(data)
        # Store history
        new_history = History(
            date_time=datetime.utcnow(),
            diary_entry=request.json.get('mood'),
            generated_image=data['img_url'],
            song_snippet=data['song'],
            user_id=current_user.id  # assuming your User model has an id field
        )
        db.session.add(new_history)
        db.session.commit()
        
        return jsonify(data)
    return render_template('index.html', data=None)

'''
@main.route('/')
def index():
    return render_template('index.html')


@main.route('/profile')
@login_required
def profile():
    return render_template('profile.html', username=current_user.name)
'''


@main.route('/profile')
@login_required
def profile():
    user_history = History.query.filter_by(user_id=current_user.id).order_by(History.date_time.desc()).all()
    return render_template('profile.html', user_name=current_user.name, history=user_history)


@main.route('/delete_history/<int:history_id>')
@login_required
def delete_history(history_id):
    record = History.query.get_or_404(history_id)
    if record.user_id != current_user.id:
        abort(403)  # Forbidden access
    db.session.delete(record)
    db.session.commit()
    flash('Record deleted.', 'success')
    return redirect(url_for('main.profile'))
