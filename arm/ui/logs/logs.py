"""
ARM route blueprint for log pages
Covers
- logs [GET]
- listlogs [GET]
- logreader [GET]
"""

import os
from pathlib import Path
from flask_login import LoginManager, login_required  # noqa: F401
from flask import render_template, request, Blueprint, send_file, session, abort
from werkzeug.routing import ValidationError

import arm.ui.utils as ui_utils
from arm.ui import app
import arm.config.config as cfg

route_logs = Blueprint('route_logs', __name__,
                       template_folder='templates',
                       static_folder='../static')


@route_logs.route('/logs')
@login_required
def logs():
    """
    This is the main page for viewing a logfile

    this holds the XHR request that sends to other routes for the data
    """
    mode = request.args.get('mode')
    logfile = request.args.get('logfile')
    if not mode or not logfile:
        abort(400, description="'mode' and 'logfile' query parameters are required")
    session["page_title"] = "Logs"

    return render_template('logview.html', file=logfile, mode=mode)


@route_logs.route('/listlogs', defaults={'path': ''})
@login_required
def listlogs(path):
    """
    The 'View logs' page - show a list of logfiles in the log folder with creation time and size
    Gives the user links to tail/arm/Full/download
    """
    base_path = cfg.arm_config['LOGPATH']
    full_path = os.path.join(base_path, path)
    session["page_title"] = "Logs"

    # Deal with bad data
    if not os.path.exists(full_path):
        abort(404, description="Log directory not found")

    # Get all files in directory
    files = ui_utils.get_info(full_path)
    return render_template('logfiles.html', files=files, date_format=cfg.arm_config['DATE_FORMAT'])


@route_logs.route('/logreader')
@login_required
def logreader():
    """
    The default logreader output function

    This will display or allow downloading the requested logfile
    This is where the XHR requests are sent when viewing /logs?=logfile
    """
    log_path = cfg.arm_config['LOGPATH']
    mode = request.args.get('mode')
    logfile = request.args.get('logfile')
    session["page_title"] = "Logs"

    # Validate BEFORE joining: a missing logfile would make os.path.join raise
    # TypeError, and validate_logfile raises non-HTTP exceptions that 500.
    if not logfile:
        abort(400, description="'logfile' query parameter is required")
    full_path = os.path.join(log_path, logfile)
    try:
        ui_utils.validate_logfile(logfile, mode, Path(full_path))
    except (ValidationError, FileNotFoundError) as log_error:
        app.logger.warning(f"Rejected logfile request '{logfile}': {log_error}")
        abort(404, description="Log file not found or invalid")

    # Only ARM logs
    if mode == "armcat":
        generate = ui_utils.generate_arm_cat(full_path)
    # Give everything / Tail
    elif mode == "full":
        generate = ui_utils.generate_full_log(full_path)
    elif mode == "download":
        return send_file(full_path, as_attachment=True)
    else:
        # No / unknown mode
        abort(400, description="Unknown log mode")

    return app.response_class(generate, mimetype='text/plain')
