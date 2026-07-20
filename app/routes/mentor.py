"""Mentor Sites page routes."""
from flask import Blueprint, render_template

mentor_bp = Blueprint("mentor", __name__)


@mentor_bp.route("/")
def index():
    return render_template("mentor/index.html")
