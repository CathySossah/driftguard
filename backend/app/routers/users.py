from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import require_admin, get_current_user
from app.services.audit_service import log_action

router = APIRouter(prefix="/users", tags=["Utilisateurs"])


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get("/", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """Liste des comptes — page 'Gestion des utilisateurs' (admin uniquement)."""
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.patch("/{user_id}/deactivate", response_model=schemas.UserOut)
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.is_active = False
    db.commit()
    db.refresh(user)
    log_action(db, action="user.deactivated", user_id=admin.id, target=f"Compte {user.full_name}")
    return user
