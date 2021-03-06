from flaskApp import app
from flask import render_template, request, flash, session, url_for, redirect, jsonify
from jinja2 import Template
from forms import ContactForm, SignupForm, SigninForm, GroupForm, DiscussionThreadForm, PitchForm, ConversationStartersForm
from flask.ext.mail import Message, Mail
from models import db, Smarketer, Group, DiscussionThread, aes_decrypt, WarehousePeople, Pitch, ConversationStarters, Replies
import subprocess
import json
import os

mail = Mail()

@app.route('/')
def home():
  return render_template('home.html')

@app.route('/about')
def about():
  return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
  form = ContactForm()

  if request.method == 'POST':
    if form.validate() == False:
      flash('All fields are required.')
      return render_template('contact.html', form=form)
    else:
      msg = Message(form.subject.data, sender='contact@derivatived.com', recipients=['james@derivatived.com'])
      msg.body = """
      From: %s <%s>
      %s
      """ % (form.name.data, form.email.data, form.message.data)
      mail.send(msg)

      return render_template('contact.html', success=True)

  elif request.method == 'GET':
    return render_template('contact.html', form=form)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
  form = SignupForm()

  if 'email' in session:
    return redirect(url_for('profile'))

  if request.method == 'POST':
    if form.validate() == False:
      return render_template('signup.html', form=form)
    else:
      newuser = Smarketer(form.firstName.data, form.username.data, form.password.data)
      db.session.add(newuser)
      db.session.commit()

      session['email'] = newuser.username
      return redirect(url_for('profile'))

  elif request.method == 'GET':
    return render_template('signup.html', form=form)

@app.route('/profile')
def profile():

  if 'email' not in session:
    return redirect(url_for('signin'))

  user = Smarketer.query.filter_by(username = session['email']).first()

  if user is None:
    return redirect(url_for('signin'))
  else:
    return render_template('profile.html')

@app.route('/addGroup', methods=['GET', 'POST'])
def addGroup():

  if 'email' not in session:
    return redirect(url_for('signin'))

  user = Smarketer.query.filter_by(username = session['email']).first()

  if user is None:
    return redirect(url_for('signin'))
  else:
    form = GroupForm()

    if request.method == 'POST':
      if form.validate() == False:
        return render_template('addGroup.html', form=form)
      else:
	totalTitle = form.groupTitle.data + " - " + form.groupID.data
        newGroup = Group(form.groupID.data, totalTitle)
        db.session.add(newGroup)
        db.session.commit()

	form.groupID.data = ""
	form.groupTitle.data = ""
        return render_template('addGroup.html', form=form, success=True)

    elif request.method == 'GET':
      return render_template('addGroup.html', form=form)

@app.route('/addPitch', methods=['GET', 'POST'])
def addPitch():

  if 'email' not in session:
    return redirect(url_for('signin'))

  user = Smarketer.query.filter_by(username = session['email']).first()

  if user is None:
    return redirect(url_for('signin'))
  else:
    form = PitchForm()

    if request.method == 'POST':
      if form.validate() == False:
        return render_template('addPitch.html', form=form)
      else:
        newPitch = Pitch(form.subject.data, form.message.data, form.pitchTitle.data)
        db.session.add(newPitch)
        db.session.commit()

        form.subject.data = ""
	form.message.data = ""
	form.pitchTitle.data = ""
	return render_template('addPitch.html', form=form, success=True)

    elif request.method == 'GET':
      return render_template('addPitch.html', form=form)

@app.route('/sendPitch', methods=['GET', 'POST'])
def sendPitch():
    if 'email' not in session:
        return redirect(url_for('signin'))

    user = Smarketer.query.filter_by(username = session['email']).first()

    if user is None:
        return redirect(url_for('signin'))
    else:
      form = ConversationStartersForm()

    if request.method == 'POST':
        if form.validate() == False:
            return render_template('sendPitch.html', form=form)

        else:
            pitch = Pitch.query.filter_by(pitchID = form.pitchID.data).first()
            discussionThread = DiscussionThread.query.filter_by(url = form.discussionThreadURL.data).first()
            number_pitches = int(form.pitchNumber.data)

            pitchWarehousePeople = WarehousePeople.query.filter_by(discussionURL = form.discussionThreadURL.data, isPitched = False).limit(number_pitches)
            script_path = os.path.abspath('./flaskApp')
            commands = ['casperjs {}/linkedin-sales.js'.format(script_path)]
            commands.append("--user='{}'".format( user.username ))
            commands.append("--pass='{}'".format( aes_decrypt(user.password) ))
            commands.append("--first-name='{}'".format( user.firstName ))
            commands.append("--cookies-file='{}-cookies.txt'".format( user.firstName ))
            commands.append("--send-pitch='{}'".format('false'))
            base_command = " ".join(commands)

            errors = "Failed IDs: "
            sentSuccess = None

            for p in xrange(number_pitches):
                warehousePerson = pitchWarehousePeople[p]

                pitch_commands = []
                pitch_commands.append("--to-user-id='{}'".format(warehousePerson.userID))

                subject = Template(pitch.subject)
                message = Template(pitch.message)

                rendered_subject =  subject.render(warehousePerson=warehousePerson,
                        discussionThread=discussionThread,
                        user=user).replace("'", "'\\''")
                rendered_message =  message.render(warehousePerson=warehousePerson,
                        discussionThread=discussionThread,
                        user=user).replace("'", "'\\''").replace('\n', '\\n')

                pitch_commands.append("--pitch-subject='{}'".format(rendered_subject))
                pitch_commands.append("--pitch-body='{}'".format(rendered_message))
                pitch_commands.append("--group-id='{}'".format(discussionThread.groupID))
                pitch_command = "{0} {1}".format(base_command, " ".join(pitch_commands))
                proc = subprocess.Popen(pitch_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output = proc.communicate()
                status = json.loads(output[0])
                # status will look like: {'sent': boolean, 'to': toUserID}
                sentSuccess = status['sent']

                if sentSuccess:
                    newConversationStarter = ConversationStarters(status['to'], user.userID, pitch.pitchID)
                    db.session.add(newConversationStarter)
                    db.session.commit()
                else:
                    errors = "{0} {1}, ".format(errors, status['to'])

            form.pitchNumber.data = ""
            return render_template('sendPitch.html', form=form, success=sentSuccess, errors=errors) #TODO: insert array to tell which ones failed

    elif request.method == 'GET':
        return render_template('sendPitch.html', form=form)

@app.route('/addDiscussionThread', methods=['GET', 'POST'])
def addDiscussionThread():
    if 'email' not in session:
        return redirect(url_for('signin'))

    user = Smarketer.query.filter_by(username = session['email']).first()

    if user is None:
        return redirect(url_for('signin'))
    else:
        form = DiscussionThreadForm()

    if request.method == 'POST':
        if form.validate() == False:
            return render_template('addDiscussionThread.html', form=form)

        else:
            savedDiscussionThread = False
            script_path = os.path.abspath('./flaskApp')
            commands = ['casperjs {}/linkedin-sales.js'.format(script_path)]
            commands.append("--user='{}'".format( user.username ))
            commands.append("--pass='{}'".format( aes_decrypt(user.password) ))
            commands.append("--first-name='{}'".format( user.firstName ))
            commands.append("--cookies-file='{}-cookies.txt'".format( user.firstName ))
            commands.append("--discuss-url='{}'".format( form.url.data ))
            command = " ".join(commands)
            proc = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
            output = proc.communicate()
            try:
                comments = json.loads(output[0])
            except:
                comments = output[0]
                return render_template('addDiscussionThread.html', isError=True, error=comments, form=form)

            for c in comments:
                userID = c["userID"]
                name = c["name"]
                firstName = c["fname"]
                lastName = c["lname"]
                byline = c["byline"]
                discussionURL = form.url.data
                likesCount = c["likes"]
                profileURL = c["profileURL"]
                isFirstDegree = c["isFirstDegree"]
                connection = c["connection"]
                imageURL = c["image_src"]
                comment = c["comment"]

                #saves new warehousePerson to database
                newWarehousePerson = WarehousePeople(userID, firstName, lastName, byline, discussionURL, comment, likesCount, profileURL, imageURL)
                if not savedDiscussionThread:
                    newDiscussionThread = DiscussionThread(form.url.data, form.groupID.data, form.title.data)
                    db.session.add(newDiscussionThread)
                    db.session.commit()
                    savedDiscussionThread = True 
                warehousePersonExists = WarehousePeople.query.filter_by(userID = userID).first()
		if warehousePersonExists == False:
                    db.session.add(newWarehousePerson)
                    db.session.commit()

            if savedDiscussionThread:
                form.title.data = ""
                form.url.data = ""
                return render_template('addDiscussionThread.html', form=form, success=savedDiscussionThread)

    elif request.method == 'GET':
      return render_template('addDiscussionThread.html', form=form)

@app.route('/signin', methods=['GET', 'POST'])
def signin():
  form = SigninForm()

  if 'email' in session:
    return redirect(url_for('profile'))

  if request.method == 'POST':
    if form.validate() == False:
      return render_template('signin.html', form=form)
    else:
      session['email'] = form.username.data
      return redirect(url_for('profile'))

  elif request.method == 'GET':
    return render_template('signin.html', form=form)

@app.route('/signout')
def signout():

  if 'email' not in session:
    return redirect(url_for('signin'))

  session.pop('email', None)
  return redirect(url_for('home'))
