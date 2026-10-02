"""Polished Streamlit AI Interview Coach."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import streamlit as st

import ai_service
import auth
import capture
import database
from live_interview import device_check, live_interview

try:
    from streamlit_webrtc import webrtc_streamer  # noqa: F401

    WEBRTC_AVAILABLE = True
except ImportError:
    WEBRTC_AVAILABLE = False

st.set_page_config(page_title="Interview Coach", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")
database.init_db()

st.markdown("""<style>
*, *::before, *::after {box-sizing:border-box;}
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {overflow-x:hidden;}
.block-container {width:100%; max-width:1220px; padding:1.5rem 1.25rem 2rem;}
/* Keep the workspace focused on the interview instead of deployment controls. */
.stDeployButton, [data-testid="stAppDeployButton"] {display: none !important;}
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {display:none !important;}
[data-testid="stHeader"] {display:none !important;}
.hero {padding: 2rem 2.2rem; border-radius: 22px; background: linear-gradient(120deg,#172554,#312e81 55%,#4338ca); color:white; margin-bottom:1.2rem; box-shadow:0 14px 35px rgba(30,41,99,.18);}
.hero h1 {font-size:2.4rem; line-height:1.15; overflow-wrap:anywhere; margin-bottom:.35rem;}
.hero p {font-size:1.05rem; opacity:.9; margin:0;}
.feature-card {padding:1rem 1.1rem; border:1px solid #e2e8f0; border-radius:16px; background:#fff; min-height:108px; box-shadow:0 4px 15px rgba(15,23,42,.04);}
.feature-card strong {display:block; margin-bottom:.3rem; color:#0f172a;}
.feature-card span {color:#64748b; font-size:.9rem;}
.section-card {padding:1.2rem 1.35rem; border-radius:18px; background:#f8fafc; border:1px solid #e2e8f0; margin:1rem 0;}
.muted {color:#64748b; font-size:.9rem;}
[data-testid="column"] {min-width:0;}
[data-testid="stHorizontalBlock"] {min-width:0;}
[data-testid="stTextInput"], [data-testid="stTextArea"], [data-testid="stSelectbox"], [data-testid="stMultiSelect"] {min-width:0;}
[data-testid="stCustomComponentV1"] {width:100% !important;}
[data-testid="stCustomComponentV1"] iframe {width:100% !important;}
@media (max-width: 640px) {
    .block-container {padding:1rem .75rem 1.5rem;}
    .hero {padding:1.25rem 1rem; border-radius:16px; margin-bottom:.9rem;}
    .hero h1 {font-size:1.8rem;}
    .hero p {font-size:.95rem; line-height:1.45;}
    .feature-card, .section-card {padding:.9rem; border-radius:12px;}
    .feature-card {min-height:0;}
    .section-card {margin:.75rem 0;}
    [data-testid="stHorizontalBlock"] {gap:.5rem;}
    [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {width:100%; white-space:normal;}
}
</style>""", unsafe_allow_html=True)


def reset():
    for key in ("session_id", "questions", "current", "evaluations", "report", "submitted", "topics", "initial_count", "adaptive_mode", "live_mode", "live_transcript", "live_last_event", "live_replay", "pending_setup", "device_checked"):
        st.session_state.pop(key, None)


def opening_question(name: str, role: str) -> str:
    return (
        f"Hi {name.strip()}, welcome to your {role} interview. "
        "To get started, please tell me about yourself, your background, "
        "and the kind of work you enjoy."
    )


def login_view():
    st.markdown(
        """<style>
        [data-testid="stSidebar"] {display:none;}
        [data-testid="stAppViewContainer"] {margin-left:0;}
        [data-testid="stHeader"] {background:transparent;}
        .block-container {max-width:760px; min-height:calc(100vh - 2rem); display:flex; flex-direction:column; justify-content:center;}
        .login-copy {text-align:center; color:#64748b; margin:-.5rem 0 1.5rem;}
        </style>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero"><h1>🎯 Welcome to Interview Coach</h1>'
        '<p>Verify your email once, then return with your username and password.</p></div>',
        unsafe_allow_html=True,
    )
    pending = st.session_state.get("pending_verification")
    if pending:
        st.subheader("Verify your email")
        st.caption(f"Enter the 6-digit code sent to {pending['email']}.")
        with st.form("verify_email"):
            code = st.text_input("Verification code", max_chars=6, placeholder="123456")
            verify = st.form_submit_button("Verify email", type="primary", width="stretch")
        if verify:
            valid = database.verify_account_email(
                pending["user_id"], auth.hash_otp(code), datetime.now(timezone.utc).isoformat()
            )
            if valid:
                st.session_state.auth_user_id = pending["user_id"]
                st.session_state.pop("pending_verification", None)
                st.rerun()
            st.error("That code is invalid or expired. Create a new account to request another code.")
        if st.button("Back to login"):
            st.session_state.pop("pending_verification", None)
            st.rerun()
        return

    pending_reset = st.session_state.get("pending_password_reset")
    if pending_reset:
        st.subheader("Reset your password")
        st.caption(f"Enter the code sent to {pending_reset['email']} and choose a new password.")
        with st.form("reset_password"):
            reset_code = st.text_input("Password reset code", max_chars=6, placeholder="123456")
            reset_password = st.text_input("New password", type="password")
            reset_confirm = st.text_input("Confirm new password", type="password")
            reset_submitted = st.form_submit_button("Reset password", type="primary", width="stretch")
        if reset_submitted:
            if len(reset_password) < 8:
                st.error("Password must be at least 8 characters.")
            elif reset_password != reset_confirm:
                st.error("Passwords do not match.")
            elif database.reset_password(
                pending_reset["user_id"], auth.hash_otp(reset_code),
                datetime.now(timezone.utc).isoformat(), auth.hash_password(reset_password),
            ):
                st.session_state.pop("pending_password_reset", None)
                st.session_state.pop("show_forgot_password", None)
                st.success("Password reset successfully. You can now log in.")
                st.rerun()
            else:
                st.error("That code is invalid or expired.")
        if st.button("Back to login", key="back_to_login_after_reset"):
            st.session_state.pop("pending_password_reset", None)
            st.rerun()
        return

    login_tab, register_tab = st.tabs(["Log in", "Create account"])
    with login_tab:
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            account = database.account_by_username(username)
            if not account or not account["password_hash"] or not auth.verify_password(password, account["password_hash"]):
                st.error("Incorrect username or password.")
            elif not account["email_verified"]:
                st.error("Verify your email before logging in.")
            else:
                st.session_state.auth_user_id = int(account["user_id"])
                st.rerun()
        if st.button("Forgot password?", key="forgot_password"):
            st.session_state.show_forgot_password = True
            st.rerun()
        if st.session_state.get("show_forgot_password"):
            st.subheader("Send a password reset code")
            with st.form("request_password_reset"):
                reset_email = st.text_input("Account email")
                request_reset = st.form_submit_button("Send reset code", width="stretch")
            if request_reset:
                smtp = st.secrets.get("smtp")
                account = database.account_by_email(reset_email)
                if not smtp:
                    st.error("Email delivery is not configured. Add the [smtp] settings to Streamlit Secrets first.")
                elif account:
                    code = auth.create_otp()
                    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                    try:
                        reset_user_id = database.begin_password_reset(
                            reset_email, auth.hash_otp(code), expires
                        )
                        auth.send_otp(
                            recipient=reset_email.strip(),
                            code=code,
                            smtp=dict(smtp),
                            subject="Your Interview Coach password reset code",
                            message_text=(
                                f"Your Interview Coach password reset code is {code}.\n\n"
                                "It expires in 10 minutes. If you did not request this, ignore this email."
                            ),
                        )
                    except Exception:
                        st.error("We could not send the reset email. Check your SMTP settings and try again.")
                    else:
                        st.session_state.pending_password_reset = {
                            "user_id": reset_user_id,
                            "email": reset_email.strip(),
                        }
                        st.rerun()
                else:
                    st.info("If an account uses that email, a reset code has been sent.")
            if st.button("Cancel", key="cancel_forgot_password"):
                st.session_state.pop("show_forgot_password", None)
                st.rerun()
    with register_tab:
        st.caption("We will email you a one-time verification code.")
        with st.form("register"):
            new_username = st.text_input("Choose a username")
            email = st.text_input("Email address")
            new_password = st.text_input("Create password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            register = st.form_submit_button("Create account", type="primary", width="stretch")
        if register:
            smtp = st.secrets.get("smtp")
            valid_username = re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", new_username.strip())
            if not valid_username:
                st.error("Username must be 3-32 characters using letters, numbers, dot, dash, or underscore.")
            elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
                st.error("Enter a valid email address.")
            elif len(new_password) < 8:
                st.error("Password must be at least 8 characters.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif not smtp:
                st.error("Email delivery is not configured. Add the [smtp] settings to Streamlit Secrets first.")
            elif database.account_by_username(new_username):
                st.error("That username is already registered. Choose another username.")
            elif database.account_by_email(email):
                st.error("That email is already registered. Log in or reset its password.")
                if st.button("Forgot password?", key="forgot_password_from_register"):
                    st.session_state.show_forgot_password = True
                    st.rerun()
            else:
                code = auth.create_otp()
                expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                try:
                    user_id = database.create_account(
                        new_username, email, auth.hash_password(new_password), auth.hash_otp(code), expires
                    )
                    auth.send_otp(recipient=email.strip(), code=code, smtp=dict(smtp))
                except Exception:
                    st.error("We could not send the verification email. Check your SMTP settings and try again.")
                else:
                    st.session_state.pending_verification = {"user_id": user_id, "email": email.strip()}
                    st.rerun()


def setup_view():
    st.markdown(
        '<div class="hero"><h1>🎯 Your next interview starts here</h1>'
        '<p>Practice with a personal AI interviewer, improve your answers, and build confidence one conversation at a time.</p></div>',
        unsafe_allow_html=True,
    )
    f1, f2, f3 = st.columns(3)
    f1.markdown('<div class="feature-card"><strong>🎙️ Real conversation</strong><span>Speak naturally with hands-free voice mode and live camera practice.</span></div>', unsafe_allow_html=True)
    f2.markdown('<div class="feature-card"><strong>🧠 Personal coaching</strong><span>Get targeted feedback, follow-up questions, and practical next steps.</span></div>', unsafe_allow_html=True)
    f3.markdown('<div class="feature-card"><strong>📈 Track your growth</strong><span>Save your attempts and see how your interview performance improves.</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-card"><h3>Build your practice session</h3><p class="muted">Tell the coach what you want to practise. You can change these settings for every attempt.</p></div>', unsafe_allow_html=True)
    with st.form("setup"):
        name = st.text_input("👋 What should the interviewer call you?", placeholder="Enter your name here")
        c1, c2 = st.columns(2)
        role = c1.text_input("🎯 Target role", "Software Engineer")
        level = c2.selectbox("📊 Experience level", ["Entry level", "Mid level", "Senior", "Staff / Lead"])
        c3, c4 = st.columns(2)
        interview_type = c3.selectbox("🧭 Interview focus", ["Mixed", "Technical", "Behavioral"])
        count = c4.slider("📝 Starting questions", 3, 10, 5)
        topics = st.multiselect(
            "💻 What would you like to practise?",
            ai_service.TOPICS,
            default=["Python", "APIs"],
            help="Choose one or more technologies. Questions are rotated across your previous attempts.",
        )
        mode_col, lang_col = st.columns(2)
        adaptive_mode = st.checkbox(
            "Adaptive interviewer mode",
            value=True,
            help="The coach asks follow-up questions based on your answers. Use Finish interview when you are ready.",
        )
        live_mode = st.checkbox(
            "🎙️ Live interview mode (hands-free)",
            value=True,
            help="The browser speaks each question, listens until you pause, evaluates your answer, and continues automatically.",
        )
        language = lang_col.selectbox(
            "Speech recognition language",
            ["English (India)", "English (US)", "English (UK)"],
            help="Choose the accent/language used to transcribe your microphone answer.",
        )
        mode_col.caption("The coach will ask follow-up questions based on your answers.")
        with st.expander("Advanced AI settings"):
            model_choice = st.selectbox(
                "Ollama model",
                [
                    "llama3.2",
                    "llama3.1",
                    "mistral",
                    "gemma2",
                    "qwen2.5",
                    "phi3",
                    "deepseek-r1",
                    "codellama",
                    "Custom model",
                ],
                help="Choose a local model installed in Ollama. If it is not installed, the app uses its fallback mode.",
            )
            model = (
                st.text_input("Custom Ollama model name", "llama3.2")
                if model_choice == "Custom model"
                else model_choice
            )
            st.caption("Install a model with `ollama pull <model-name>` before using it.")
        submitted = st.form_submit_button("🚀 Start my interview", type="primary", use_container_width=True)
    if submitted:
        if not name.strip() or not role.strip():
            st.error("Please provide your name and target role.")
            return
        with st.spinner("Preparing your interview..."):
            user_id = st.session_state.auth_user_id
            session_id = database.create_session(user_id, role, level, interview_type, count, topics)
            questions = ai_service.generate_questions(
                role, level, interview_type, count, model, topics, database.prior_questions(user_id),
                use_ai=not live_mode,
            )
            if questions:
                questions[0] = opening_question(name, role)
            database.save_questions(session_id, questions)
        st.session_state.update(session_id=session_id, questions=questions, current=0, evaluations=[],
                                model=model, role=role, name=name, topics=topics, initial_count=count,
                                adaptive_mode=adaptive_mode, live_mode=live_mode, language=language, live_transcript=[],
                                live_last_event=None, live_replay=0, welcome_played=False)
        st.rerun()


def device_check_view():
    st.markdown(
        """<style>
        [data-testid="stSidebar"] {display:none;}
        [data-testid="stAppViewContainer"] {margin-left:0;}
        [data-testid="stHeader"] {background:transparent;}
        .block-container {max-width:1100px; min-height:calc(100vh - 2rem); display:flex; flex-direction:column; justify-content:center;}
        </style>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero"><h1>📹 Check your camera and microphone</h1>'
        '<p>We will check your devices first. Once they work, you can continue to the interview setup.</p></div>',
        unsafe_allow_html=True,
    )
    st.info("Allow camera and microphone access when your browser asks. Say a few words so the microphone meter can confirm your input.")
    result = device_check(key="device_check")
    if result and result.get("type") == "device_ready":
        st.session_state.device_checked = True
        st.rerun()


def interview_view():
    questions = st.session_state.questions
    index = st.session_state.current
    st.progress(index / len(questions), text=f"Question {index + 1} of {len(questions)}")
    st.header("Your interview")
    st.caption(f"Target role: {st.session_state.role} • Topics: {', '.join(st.session_state.topics)} • Take your time and answer naturally.")
    if index == 0:
        st.chat_message("assistant", avatar="🎙️").write(
            f"Hi {st.session_state.name}! Welcome to your interview. "
            "I’ll ask you questions one at a time and give you coaching after each answer."
        )
        if st.button("🔊 Hear welcome", key="hear_welcome"):
            welcome_audio = capture.question_audio(
                f"Hi {st.session_state.name}! Welcome to your interview. "
                "To get started, please tell me about yourself, your background, "
                "and the kind of work you enjoy."
            )
            if welcome_audio:
                st.audio(welcome_audio, format="audio/mp3")
            else:
                st.info("Welcome audio is unavailable. You can read the interviewer message above.")
    if st.session_state.get("adaptive_mode") and st.button("Finish interview and show report", key=f"finish_{index}"):
        if st.session_state.evaluations:
            st.session_state.current = len(st.session_state.questions)
            st.rerun()
        st.info("Answer at least one question before finishing.")
    question = questions[index]
    st.markdown(f"### {question}")
    if st.session_state.get("live_mode"):
        st.info("🎙️ **Live interview is on.** Your browser will speak, listen for a pause, and continue without button clicks.")
        st.caption("Supported in Chrome/Edge desktop. Keep your speaker volume moderate and use headphones when possible to prevent the question audio from entering your answer.")
        if WEBRTC_AVAILABLE:
            st.subheader("📹 Your live camera")
            st.caption("Keep this view large and centered while you answer. Your microphone is handled by the interviewer below.")
            capture.live_stream("live_camera_preview", audio=False)
        else:
            st.warning("Live camera/microphone preview is unavailable. Install `streamlit-webrtc` to enable it.")
        event = live_interview(
            question,
            greeting=f"Hi {st.session_state.name}, welcome to your interview." if index == 0 else "",
            replay=st.session_state.get("live_replay", 0),
            key="live_interview",
        )
        st.markdown("#### 🎙️ Interviewer is asking")
        st.info(question)
        st.markdown("#### Live transcript")
        for item in st.session_state.get("live_transcript", []):
            with st.chat_message("assistant"):
                st.write(item["question"])
            with st.chat_message("user"):
                st.write(item["answer"])
            st.caption(f"Coach score: {item['evaluation']['score']}/10 — {item['evaluation']['feedback']}")
        if event and event.get("type") == "answer" and event.get("at") != st.session_state.get("live_last_event"):
            answer = event.get("text", "").strip()
            if not answer and event.get("audio"):
                with st.spinner("Converting your answer to text…"):
                    language_code = {
                        "English (India)": "en-IN",
                        "English (US)": "en-US",
                        "English (UK)": "en-GB",
                    }.get(st.session_state.get("language"), "en-IN")
                    answer, transcription_error = capture.transcribe_base64_wav(event["audio"], language_code)
                if not answer:
                    st.warning(transcription_error or "I could not transcribe that recording. Please try again.")
            st.session_state.live_last_event = event.get("at")
            if answer:
                command = " ".join(answer.casefold().replace("please", "").split())
                if command in {
                    "repeat",
                    "repeat again",
                    "say that again",
                    "say it again",
                    "can you repeat",
                    "i did not hear",
                    "i didn't hear",
                    "could you repeat",
                }:
                    st.session_state.live_replay = st.session_state.get("live_replay", 0) + 1
                    st.session_state.live_last_event = None
                    st.rerun()
                with st.spinner("Evaluating your answer…"):
                    evaluation = ai_service.evaluate_answer(
                        question, answer, st.session_state.model, fast=True
                    )
                question_rows = database.get_questions(st.session_state.session_id)
                database.save_answer(question_rows[index]["question_id"], {"answer": answer, **evaluation})
                st.session_state.evaluations.append(evaluation)
                st.session_state.live_transcript.append({"question": question, "answer": answer, "evaluation": evaluation})
                follow_up = evaluation.get("follow_up_question")
                max_questions = 50 if st.session_state.get("adaptive_mode") else 2 * st.session_state.initial_count
                if follow_up and len(st.session_state.questions) < max_questions:
                    database.save_question(st.session_state.session_id, follow_up)
                    st.session_state.questions.append(follow_up)
                st.session_state.current += 1
                st.rerun()
        if st.button("Stop live mode and switch to typed answers", key=f"stop_live_{index}"):
            st.session_state.live_mode = False
            st.rerun()
        return
    if st.button("🔊 Hear question", key=f"speak_{index}"):
        with st.spinner("Preparing audio..."):
            question_audio = capture.question_audio(question)
        if question_audio:
            st.audio(question_audio, format="audio/mp3")
        else:
            st.info("Question audio is unavailable. You can read the text above.")
    pending_transcript = st.session_state.pop(f"transcript_{index}", None)
    if pending_transcript:
        st.session_state[f"answer_{index}"] = pending_transcript
    answer = st.text_area("Type your answer", height=190, placeholder="Structure your response with context, actions, and outcomes.", key=f"answer_{index}")
    audio_ok, audio_message = capture.available()
    with st.expander("Optional camera / audio capture"):
        st.caption("Camera guidance: use the preview to self-check upright posture, framing, and natural eye contact with the camera. "
                   "This app does not claim to perform eye tracking or assess appearance.")
        if WEBRTC_AVAILABLE:
            capture.live_stream(f"live_{index}")
        else:
            st.camera_input("Camera preview", key=f"camera_{index}")
            st.info("Install streamlit-webrtc for a live camera/microphone preview.")
        if audio_ok:
            recording = capture.audio_input(f"audio_{index}")
            if recording and recording.get("bytes"):
                st.success("Audio captured.")
                if st.button("Transcribe recording", key=f"transcribe_{index}"):
                    with st.spinner("Transcribing..."):
                        language_code = {
                            "English (India)": "en-IN",
                            "English (US)": "en-US",
                            "English (UK)": "en-GB",
                        }.get(st.session_state.get("language"), "en-IN")
                        text, error = capture.transcribe_audio(recording["bytes"], language_code)
                    if text:
                        st.session_state[f"transcript_{index}"] = text
                        st.success("Transcript added to the answer box.")
                        st.rerun()
                    st.warning(error or "Could not transcribe audio.")
        else:
            st.info(audio_message)
        st.checkbox("I reviewed my posture, eye contact, and speaking pace.", key=f"reviewed_{index}")
    if st.button("Submit answer →", type="primary", disabled=not answer.strip()):
        with st.spinner("Analyzing your answer..."):
            evaluation = ai_service.evaluate_answer(question, answer, st.session_state.model)
        question_rows = database.get_questions(st.session_state.session_id)
        database.save_answer(question_rows[index]["question_id"], {"answer": answer, **evaluation})
        st.session_state.evaluations.append(evaluation)
        follow_up = evaluation.get("follow_up_question")
        max_questions = 50 if st.session_state.get("adaptive_mode") else 2 * st.session_state.initial_count
        if follow_up and len(st.session_state.questions) < max_questions:
            database.save_question(st.session_state.session_id, follow_up)
            st.session_state.questions.append(follow_up)
        st.session_state.current += 1
        st.rerun()


def report_view():
    if "report" not in st.session_state:
        with st.spinner("Building your coaching report..."):
            report = ai_service.build_report(st.session_state.evaluations, st.session_state.model)
            database.finish_session(st.session_state.session_id, report)
            st.session_state.report = report
    report = st.session_state.report
    st.balloons()
    st.markdown('<div class="hero"><h1>Interview complete 🎉</h1><p>Here is your personalized practice report.</p></div>', unsafe_allow_html=True)
    st.metric("Overall score", f"{report['overall_score']}/10")
    c1, c2, c3 = st.columns(3)
    c1.subheader("Strengths")
    c1.markdown("\n".join(f"- {item}" for item in report["strengths"]))
    c2.subheader("Growth areas")
    c2.markdown("\n".join(f"- {item}" for item in report["weaknesses"]))
    c3.subheader("Next steps")
    c3.markdown("\n".join(f"- {item}" for item in report["recommendations"]))
    st.subheader("Answer-by-answer coaching")
    for number, (question, evaluation) in enumerate(zip(st.session_state.questions, st.session_state.evaluations), 1):
        with st.expander(f"{number}. {question} — {evaluation['score']}/10"):
            st.write(evaluation["feedback"])
            st.caption(f"Try this: {evaluation['suggestion']}")
    if st.button("Start another interview", type="primary"):
        reset()
        st.rerun()


def dashboard():
    st.sidebar.title("Interview Coach")
    st.sidebar.caption("Signed in")
    if st.sidebar.button("Log out", use_container_width=True):
        st.session_state.pop("auth_user_id", None)
        reset()
        st.rerun()
    if st.sidebar.button("＋ New interview", use_container_width=True):
        reset()
        st.rerun()
    st.sidebar.divider()
    st.sidebar.subheader("Recent progress")
    rows = database.history()
    if not rows:
        st.sidebar.caption("Complete your first interview to see progress here.")
    for row in rows:
        st.sidebar.write(f"**{row['overall_score']:.1f}/10** · {row['job_role']}")
        st.sidebar.caption(row["created_at"][:10])


if not st.session_state.get("auth_user_id"):
    login_view()
    st.stop()

dashboard()
if "session_id" not in st.session_state:
    if not st.session_state.get("device_checked"):
        device_check_view()
    else:
        setup_view()
elif st.session_state.current < len(st.session_state.questions):
    interview_view()
else:
    report_view()
