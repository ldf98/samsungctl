# -*- coding: utf-8 -*-

import flask
import os
import sys

app = flask.Flask('Encrypted XML Provider')


@app.route('/smp_15_/smp_17_', methods=['POST'])
def smp_17_():
    '''smp_16_'''
    print 'DATA:'
    print flask.request.data
    print
    print
    print
    print 'HEADERS:'
    print flask.request.headers
    return ''

app.run(host='0.0.0.0', port=5000)
