Installation from source
------------------------

Additional requirements:

- ``git``
- ``redis`` and ``hiredis`` library
- ``virtualenv``
- C compiler and development libraries needed to build dependencies

  - CentOS: ``gcc libffi-devel openssl-devel postgresql-devel libjpeg-devel zlib-devel python-devel``
  - Ubuntu: ``gcc libffi-dev libsasl2-dev libssl-dev libpq-dev libjpeg8-dev zlib1g-dev python-dev``

**Waldur Core installation**

1. Get the code:

  .. code-block:: bash

    git clone https://github.com/opennode/waldur-core.git

2. Create a Virtualenv and update Setuptools:

  .. code-block:: bash

    cd waldur-core
    virtualenv venv
    venv/bin/pip install --upgrade setuptools

3. Install Waldur in development mode along with dependencies:

  .. code-block:: bash

    venv/bin/python setup.py develop

4. Create and edit settings file (see 'Configuration' section for details):

  .. code-block:: bash

    cp nodeconductor/server/settings.py.example nodeconductor/server/settings.py
    vi nodeconductor/server/settings.py

5. Initialise database -- SQLite3 database will be created in ``./db.sqlite3`` unless specified otherwise in settings files:

  .. code-block:: bash

    venv/bin/waldur migrate --noinput

6. Collect static data -- static files will be copied to ``./static/`` in the same directory:

  .. code-block:: bash

    venv/bin/waldur collectstatic --noinput

7. Start Waldur:

  .. code-block:: bash

    venv/bin/waldur runserver

Configuration
+++++++++++++

Instructions are here: http://docs.waldur.com/MasterMind+configuration
