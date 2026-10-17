# AirGuard Web Microphone Sender

This is one Django website that captures audio from the browser and sends it over WebRTC. The AirGuard Parent Android app receives the stream in **Device → Website Mic Listener**. Both sides exchange the offer, answer, and ICE candidates through the AirGuard Firestore project.

## Run locally

1. Install Python 3.10 or newer.
2. In this folder, run `py -m venv .venv`, then activate it.
3. Install packages with `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env`. Set a long random `DJANGO_SECRET_KEY` and copy `FIREBASE_API_KEY` from the AirGuard Android `google-services.json` file. Keep `.env` private.
5. Run `py manage.py runserver` and open `http://127.0.0.1:8000/`.
6. On the Parent app, open **Device → Website Mic Listener** and enter the code displayed by the website.

Microphone access requires HTTPS on deployed hosts; browsers allow it on localhost during development. For devices on different networks, configure TURN credentials in `WEBRTC_ICE_SERVERS` for reliable connectivity. STUN alone may not connect through restrictive NATs or mobile networks.

The page requests microphone permission when opened, then immediately stops that permission check. Audio capture starts only when the central button is pressed. If permission was denied, browser site settings may need to be changed before retrying.

## Notes

- The Django server proxies Firestore REST calls so the Firebase API key is not placed in browser JavaScript.
- Session documents live in `web_audio_sessions`, with nested `sender_candidates` and `receiver_candidates` collections.
- The Android Parent app must use the same Firestore database and allow its signed-in account to read and write these paths.
- Deploy this behind an HTTPS reverse proxy, set `DJANGO_DEBUG=False`, and set `DJANGO_ALLOWED_HOSTS` before public use.
