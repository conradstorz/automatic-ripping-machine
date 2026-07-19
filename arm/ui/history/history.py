"""
ARM route blueprint for history pages
Covers
- history [GET]
"""

import os
from datetime import timedelta
from flask_login import LoginManager, login_required  # noqa: F401
from flask import render_template, request, Blueprint, session

import arm.ui.utils as ui_utils
from arm.ui import app, db
from arm.models.job import Job
from arm.ui.history.filters import normalize_status, parse_date, build_page_args
import arm.config.config as cfg

route_history = Blueprint('route_history', __name__,
                          template_folder='templates',
                          static_folder='../static')

# This attaches the armui_cfg globally to let the users use any bootswatch skin from cdn
armui_cfg = ui_utils.arm_db_cfg()


@route_history.route('/history')
@login_required
def history():
    """
    Smaller much simpler output of previously run jobs

    """
    # regenerate the armui_cfg we don't want old settings
    armui_cfg = ui_utils.arm_db_cfg()
    page = request.args.get('page', 1, type=int)

    status = normalize_status(request.args.get('status', 'all'))
    date_from = parse_date(request.args.get('from'))
    date_to = parse_date(request.args.get('to'))
    from_str = date_from.strftime("%Y-%m-%d") if date_from else ""
    to_str = date_to.strftime("%Y-%m-%d") if date_to else ""

    if os.path.isfile(cfg.arm_config['DBFILE']):
        query = Job.query
        if status == "success":
            query = query.filter(Job.status == "success")
        elif status == "fail":
            query = query.filter(Job.status == "fail")
        elif status == "active":
            query = query.filter(~Job.finished)
        if date_from is not None:
            query = query.filter(Job.start_time >= date_from)
        if date_to is not None:
            query = query.filter(Job.start_time < date_to + timedelta(days=1))
        jobs = query.order_by(db.desc(Job.job_id)).paginate(
            page=page, max_per_page=int(armui_cfg.database_limit), error_out=False)
        job_items = jobs.items
        db_missing = False
    else:
        app.logger.error('ERROR: /history database file doesnt exist')
        jobs = None
        job_items = []
        db_missing = True
    app.logger.debug(f"Date format - {cfg.arm_config['DATE_FORMAT']}")

    session["page_title"] = "History"

    return render_template('history.html', jobs=job_items,
                           date_format=cfg.arm_config['DATE_FORMAT'], pages=jobs,
                           db_missing=db_missing,
                           status=status, date_from=from_str, date_to=to_str,
                           page_args=build_page_args(status, from_str, to_str))
