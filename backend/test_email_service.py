"""
Test du service d'e-mails d'alerte (sans réseau, sans serveur) :
    python test_email_service.py
"""
import json
import os
import smtplib
import urllib.error
import urllib.request

from app.services import email_service as es

for var in ("EMAIL_FROM", "BREVO_API_KEY", "SMTP_HOST", "RESEND_API_KEY"):
    os.environ.pop(var, None)

print("=== 1. Détection du mode d'envoi ===")
assert es.provider() is None
os.environ["EMAIL_FROM"] = "alertes@exemple.com"
assert es.provider() is None                       # expéditeur seul : pas assez
os.environ["SMTP_HOST"] = "smtp.exemple.com"
assert es.provider() == "smtp"
os.environ["BREVO_API_KEY"] = "cle-secrete"
assert es.provider() == "brevo"                    # Brevo prioritaire sur SMTP (HTTPS, fonctionne sur Render gratuit)
os.environ["RESEND_API_KEY"] = "re_cle"
assert es.provider() == "resend"                   # Resend prioritaire (gratuit)
del os.environ["RESEND_API_KEY"]
os.environ.pop("EMAIL_FROM")
os.environ["RESEND_API_KEY"] = "re_cle"
assert es.provider() == "resend"                   # Resend n'exige pas EMAIL_FROM
del os.environ["RESEND_API_KEY"]
os.environ["EMAIL_FROM"] = "alertes@exemple.com"
try:
    del os.environ["BREVO_API_KEY"], os.environ["SMTP_HOST"], os.environ["EMAIL_FROM"]
    es.send_email(["a@b.c"], "x", "y")
    raise SystemExit("devrait échouer sans configuration")
except es.EmailError as e:
    print("   sans configuration :", e)

print("=== 2. Corps de l'e-mail d'alerte ===")
subject, body = es.build_alert_email(
    "Transactions mobile money", 3, "critique", 0.6, 0.2,
    {"purchase_hour": {"drifted": True, "p_value": 0.0004, "threshold": 0.05, "kind": "p_value"},
     "device_type": {"drifted": False, "p_value": 0.7, "threshold": 0.05, "kind": "p_value"}},
    "https://driftguard-web.onrender.com/alerts",
)
print("  ", subject)
assert "critique" in subject and "Transactions mobile money v3" in subject
assert "60 %" in body and "20 %" in body and "purchase_hour" in body and "device_type" not in body
assert "https://driftguard-web.onrender.com/alerts" in body
assert "Aucun ré-entraînement" in body

print("=== 3. Envoi via l'API Brevo (requête simulée) ===")
os.environ.update({"EMAIL_FROM": "alertes@exemple.com", "BREVO_API_KEY": "cle-secrete"})
captured = {}


class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_urlopen(request, timeout=None):
    captured["url"] = request.full_url
    captured["headers"] = {k.lower(): v for k, v in request.header_items()}
    captured["body"] = json.loads(request.data.decode("utf-8"))
    captured["timeout"] = timeout
    return FakeResponse()


real_urlopen = urllib.request.urlopen
urllib.request.urlopen = fake_urlopen
es.send_email(["admin1@x.com", "admin2@x.com"], "Sujet", "Corps")
urllib.request.urlopen = real_urlopen
assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
assert captured["headers"]["api-key"] == "cle-secrete"
assert captured["body"]["sender"]["email"] == "alertes@exemple.com"
assert [t["email"] for t in captured["body"]["to"]] == ["admin1@x.com", "admin2@x.com"]
assert captured["body"]["subject"] == "Sujet" and captured["body"]["textContent"] == "Corps"
print("   requête conforme :", captured["body"]["to"])

print("=== 4. Envoi via SMTP (serveur simulé) ===")
del os.environ["BREVO_API_KEY"]
os.environ.update({"SMTP_HOST": "smtp.exemple.com", "SMTP_PORT": "587", "SMTP_USER": "u", "SMTP_PASSWORD": "p"})
log = []


class FakeSMTP:
    def __init__(self, host, port, timeout=None): log.append(("connect", host, port))
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): log.append("starttls")
    def login(self, u, p): log.append(("login", u))
    def send_message(self, m): log.append(("send", m["To"], m["Subject"]))


real_smtp = smtplib.SMTP
smtplib.SMTP = FakeSMTP
es.send_email(["admin@x.com"], "Sujet SMTP", "Corps")
smtplib.SMTP = real_smtp
assert log == [("connect", "smtp.exemple.com", 587), "starttls", ("login", "u"), ("send", "admin@x.com", "Sujet SMTP")], log
print("   séquence SMTP correcte")

print("=== 4 bis. Envoi via l'API Resend (requêtes simulées) ===")
for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"):
    os.environ.pop(var, None)
os.environ.pop("EMAIL_FROM", None)
os.environ["RESEND_API_KEY"] = "re_secret"
calls = []


class FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, body):
        super().__init__("https://api.resend.com/emails", code, "err", {}, None)
        self._body = body.encode("utf-8")

    def read(self, *a):
        return self._body


def resend_urlopen(request, timeout=None):
    body = json.loads(request.data.decode("utf-8"))
    calls.append((request.full_url, {k.lower(): v for k, v in request.header_items()}, body))
    if body["to"] == ["refuse@x.com"]:
        raise FakeHTTPError(403, '{"message":"You can only send testing emails to your own email address"}')
    return FakeResponse()


urllib.request.urlopen = resend_urlopen
es.send_email(["owner@x.com"], "Sujet R", "Corps R")
url, headers, body = calls[-1]
assert url == "https://api.resend.com/emails"
assert headers["authorization"] == "Bearer re_secret" and headers["user-agent"].startswith("DriftGuard")
assert body == {"from": "DriftGuard <onboarding@resend.dev>", "to": ["owner@x.com"], "subject": "Sujet R", "text": "Corps R"}
print("   requête conforme, expéditeur par défaut :", body["from"])

calls.clear()
es.send_email(["owner@x.com", "refuse@x.com"], "S", "C")       # un destinataire refusé : pas d'échec global
assert [c[2]["to"] for c in calls] == [["owner@x.com"], ["refuse@x.com"]]
print("   destinataire refusé toléré tant qu'un autre a reçu le message")

try:
    es.send_email(["refuse@x.com"], "S", "C")
    raise SystemExit("devrait échouer quand personne ne reçoit le message")
except es.EmailError as e:
    assert "403" in str(e) and "compte" in str(e)
    print("   ", e)

os.environ["EMAIL_FROM"] = "Alertes <alertes@mondomaine.com>"
calls.clear()
es.send_email(["owner@x.com"], "S", "C")
assert calls[-1][2]["from"] == "Alertes <alertes@mondomaine.com>"
os.environ["EMAIL_FROM"] = "alertes@mondomaine.com"
es.send_email(["owner@x.com"], "S", "C")
assert calls[-1][2]["from"] == "DriftGuard <alertes@mondomaine.com>"
print("   EMAIL_FROM personnalisé respecté")
urllib.request.urlopen = real_urlopen
del os.environ["RESEND_API_KEY"], os.environ["EMAIL_FROM"]

print("=== 5. Erreurs lisibles ===")
os.environ["EMAIL_FROM"] = "alertes@exemple.com"


def failing_urlopen(request, timeout=None):
    raise OSError("réseau coupé")


os.environ.update({"BREVO_API_KEY": "cle"})
urllib.request.urlopen = failing_urlopen
try:
    es.send_email(["a@b.c"], "x", "y")
    raise SystemExit("devrait échouer")
except es.EmailError as e:
    print("  ", e)
finally:
    urllib.request.urlopen = real_urlopen
try:
    es.send_email([], "x", "y")
    raise SystemExit("devrait refuser sans destinataire")
except es.EmailError:
    pass

print("\n✅ test_email_service : OK")
