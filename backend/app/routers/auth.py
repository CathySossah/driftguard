import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import hash_password, verify_password, create_access_token
from app.services.audit_service import log_action

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Créer un compte (page 'Créer un utilisateur' de la maquette).

    Créer un compte ADMINISTRATEUR exige le code d'invitation défini par la
    variable d'environnement ADMIN_SIGNUP_CODE. Si cette variable n'est pas
    définie (développement local), la création reste libre — en déploiement,
    elle doit toujours être définie.
    """
    if payload.role == models.RoleEnum.admin:
        expected = os.getenv("ADMIN_SIGNUP_CODE")
        if expected:
            given = payload.admin_code or ""
            if not hmac.compare_digest(given.encode(), expected.encode()):
                raise HTTPException(
                    status_code=403,
                    detail="Code d'invitation administrateur invalide ou manquant.",
                )

    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet e-mail")

    user = models.User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, action="user.created", user_id=user.id, target=f"Compte {user.full_name} ({user.role.value})")
    return user


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Connexion : renvoie un token JWT à utiliser dans l'en-tête Authorization."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Ce compte a été désactivé")

    token = create_access_token(data={"sub": user.id, "role": user.role.value})
    return schemas.Token(access_token=token)
