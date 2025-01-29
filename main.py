from flask import Flask
from flask import request, render_template, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from base64 import b64encode

app = Flask(__name__)
app.secret_key = 'projektowo'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# klasy danych do przechowywania
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_name = db.Column(db.String(80), nullable=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    nick = db.Column(db.String(150), nullable=False)

class Friend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# FUnkcja do zapisywania hasła w sposób bezpieczniejszy
def zaszyfruj(haslo):
    wynik = []
    klucz = "GomezNieWiedzial"
    dl = len(klucz)

    for i, znak in enumerate(haslo):
        znak_k = klucz[i % dl]  # Powtarzanie klucza, jeśli jest krótszy niż tekst
        znak_nowy = chr((ord(znak) + ord(znak_k)) % 256)
        wynik.append(znak_nowy)

    # Złączenie szyfrowanych znaków w jeden ciąg
    wynik_tekstowy = ''.join(wynik)

    wynik_tekstowy  = b64encode(wynik_tekstowy.encode()).decode()

    return wynik_tekstowy


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    return render_template('index.html', user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.password == zaszyfruj(password):
            login_user(user)
            flash('Zalogowano pomyślnie!', 'success')
            return redirect(url_for('chat'))
        else:
            flash('Zły login lub hasło', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        nick = request.form['nick']

        if User.query.filter_by(username=username).first():
            flash('Użytkownik o takiej nazwie już istnieje. Wybierz inną nazwę.', 'danger')
        else:
            new_user = User(username=username, password=zaszyfruj(password), nick=nick)  # Note: Hash your passwords in production!
            db.session.add(new_user)
            db.session.commit()
            flash('Pomyślnie zarejestrowano.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

# Funckjonalności dla zalogowanych użytkowników.
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Wylogowano.', 'info')
    return redirect(url_for('home'))

@app.route('/chat')
@login_required
def chat():
    friends = Friend.query.filter_by(user_id=current_user.id).all()
    friend_list = [User.query.get(friend.friend_id) for friend in friends]
    return render_template('home.html', friends=friend_list)

@app.route('/add_friend', methods=['POST'])
@login_required
def add_friend():
    data = request.get_json()
    username = data.get('username')
    friend = User.query.filter_by(username=username).first()
    if not friend:
        return jsonify({'error': 'User not found'}), 404

    # Check if already friends
    existing_friendship = Friend.query.filter_by(user_id=current_user.id, friend_id=friend.id).first()
    if existing_friendship:
        return jsonify({'error': 'Already friends'}), 400

    # Add friendship in both directions
    new_friend = Friend(user_id=current_user.id, friend_id=friend.id)
    reverse_friend = Friend(user_id=friend.id, friend_id=current_user.id)
    db.session.add(new_friend)
    db.session.add(reverse_friend)
    db.session.commit()
    return jsonify({'success': True, 'friend_id': friend.id, 'nick': friend.nick}), 200

@app.route('/remove_friend', methods=['POST'])
@login_required
def remove_friend():
    data = request.get_json()
    friend_id = data.get('friend_id')

    if not friend_id:
        return jsonify({'error': 'Invalid input'}), 400

    Friend.query.filter_by(user_id=current_user.id, friend_id=friend_id).delete()
    Friend.query.filter_by(user_id=friend_id, friend_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True}), 200

@app.route('/messages/<int:friend_id>', methods=['GET'])
@login_required
def get_messages(friend_id):
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == friend_id)) |
        ((Message.sender_id == friend_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()

    return jsonify([
        {
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'sender_name': msg.sender_name
        }
        for msg in messages
    ])

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    content = data.get('content')

    if not receiver_id or not content:
        return jsonify({'error': 'Invalid input'}), 400

    receiver = User.query.get(receiver_id)
    if not receiver:
        return jsonify({'error': 'Receiver not found'}), 404

    sender_nick = current_user.nick

    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content,
        sender_name=current_user.nick,
    )
    db.session.add(message)
    db.session.commit()
    return jsonify({'success': True}), 200

if __name__ == '__main__':
    #with app.app_context():
    #    db.create_all()
    app.run(debug=True)

#Działa ładnie :D