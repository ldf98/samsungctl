# -*- coding: utf-8 -*-

import flask
import os
import sys

app = flask.Flask('Encrypted XML Provider')

@app.route('/smp_2_')
def smp_2_():
    return 'smp_2_.xml'

@app.route('/smp_2_/smp_3_')
def smp_3_():
    return 'smp_2_/smp_3_.xml'


app.run(host='0.0.0.0', port=5000)
