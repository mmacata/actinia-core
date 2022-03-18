# -*- coding: utf-8 -*-
#######
# actinia-core - an open source REST API for scalable, distributed, high
# performance processing of geographical data that uses GRASS GIS for
# computational tasks. For details, see https://actinia.mundialis.de/
#
# Copyright (c) 2016-2022 Sören Gebbert and mundialis GmbH & Co. KG
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#######

"""
Mapset management resources

* List all mapsets
* Create mapset, Delete mapset, Get info about a mapset
* Lock mapset, unlock mapset, get mapset lock status
"""

import shutil
from flask import jsonify, make_response
from flask_restful_swagger_2 import swagger
import pickle
from actinia_api.swagger2.actinia_core.schemas.mapset_management import \
    MapsetLockManagementResponseModel

from actinia_core.processing.actinia_processing.ephemeral.persistent_processing \
     import PersistentProcessing
from actinia_core.rest.base.resource_base import ResourceBase
from actinia_core.core.common.app import auth
from actinia_core.core.common.api_logger import log_api_call
from actinia_core.core.common.redis_interface import enqueue_job
from actinia_core.core.common.exceptions import AsyncProcessError
from actinia_core.rest.base.user_auth import check_user_permissions
from actinia_core.rest.base.user_auth import very_admin_role
from actinia_core.models.response_models import ProcessingResponseModel, \
    StringListProcessingResultResponseModel, MapsetInfoResponseModel, \
    RegionModel, ProcessingErrorResponseModel
# from actinia_core.models.response_models import MapsetInfoModel
from actinia_core.processing.common.mapset_management import \
     list_raster_mapsets, read_current_region, create_mapset, \
     delete_mapset, get_mapset_lock, lock_mapset, unlock_mapset

__license__ = "GPLv3"
__author__ = "Sören Gebbert, Carmen Tawalika"
__copyright__ = "Copyright 2016-2022, Sören Gebbert and mundialis GmbH & Co. KG"
__maintainer__ = "mundialis"


class ListMapsetsResource(ResourceBase):
    """List all mapsets in a location
    """
    layer_type = None

    @swagger.doc({
        'tags': ['Mapset Management'],
        'description': 'Get a list of all mapsets that are located in a '
                       'specific location. '
                       'Minimum required user role: user.',
        'parameters': [
            {
                'name': 'location_name',
                'description': 'The name of the location',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'nc_spm_08'
            }
        ],
        'responses': {
            '200': {
                'description': 'This response returns a list of mapset names '
                               'and the log of the process chain that was used '
                               'to create the response.',
                'schema': StringListProcessingResultResponseModel
            },
            '400': {
                'description': 'The error message and a detailed log why listing of '
                               'mapsets did not succeeded',
                'schema': ProcessingErrorResponseModel
            }
        }
    })
    def get(self, location_name):
        """Get a list of all mapsets that are located in a specific location.
        """
        rdc = self.preprocess(has_json=False, has_xml=False,
                              location_name=location_name,
                              mapset_name="PERMANENT")
        if rdc:
            enqueue_job(self.job_timeout, list_raster_mapsets, rdc)
            http_code, response_model = self.wait_until_finish()
        else:
            http_code, response_model = pickle.loads(self.response_data)

        return make_response(jsonify(response_model), http_code)


class MapsetManagementResourceUser(ResourceBase):
    """This class returns information about a mapsets
    """

    def __init__(self):
        ResourceBase.__init__(self)

    @swagger.doc({
        'tags': ['Mapset Management'],
        'description': 'Get the current computational region of the mapset and the '
                       'projection of the location as WKT string. Minimum required '
                       'user role: user.',
        'parameters': [
            {
                'name': 'location_name',
                'description': 'The name of the location',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'nc_spm_08'
            },
            {
                'name': 'mapset_name',
                'description': 'The name of the mapset',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'PERMANENT'
            }
        ],
        'responses': {
            '200': {
                'description': 'The current computational region of the '
                               'mapset and the projection of the location',
                'schema': MapsetInfoResponseModel
            },
            '400': {
                'description': 'The error message and a detailed error log',
                'schema': ProcessingErrorResponseModel
            }
        }
    })
    def get(self, location_name, mapset_name):
        """Get the current computational region of the mapset and the projection
        of the location as WKT string.
        """
        rdc = self.preprocess(has_json=False, has_xml=False,
                              location_name=location_name,
                              mapset_name=mapset_name)

        enqueue_job(self.job_timeout, read_current_region, rdc)
        http_code, response_model = self.wait_until_finish()
        return make_response(jsonify(response_model), http_code)


class MapsetManagementResourceAdmin(ResourceBase):
    """This class manages the creation, deletion and modification of a mapsets

    This is only allowed for administrators
    """
    decorators = [log_api_call, check_user_permissions,
                  very_admin_role, auth.login_required]

    def __init__(self):
        ResourceBase.__init__(self)

    @swagger.doc({
        'tags': ['Mapset Management'],
        'description': 'Create a new mapset in an existing location. Minimum '
                       'required user role: admin.',
        'parameters': [
            {
                'name': 'location_name',
                'description': 'The name of the location',
                'required': True,
                'in': 'path',
                'type': 'string'
            },
            {
                'name': 'mapset_name',
                'description': 'The name of the mapset',
                'required': True,
                'in': 'path',
                'type': 'string'
            }
        ],
        'responses': {
            '200': {
                'description': 'Success message for mapset creation',
                'schema': ProcessingResponseModel
            },
            '400': {
                'description': 'The error message and a detailed error log',
                'schema': ProcessingErrorResponseModel
            }
        }
    })
    def post(self, location_name, mapset_name):
        """Create a new mapset in an existing location.
        """
        rdc = self.preprocess(has_json=False, has_xml=False,
                              location_name=location_name,
                              mapset_name=mapset_name)

        enqueue_job(self.job_timeout, create_mapset, rdc)
        http_code, response_model = self.wait_until_finish()
        return make_response(jsonify(response_model), http_code)

    def put(self, location_name, mapset_name):
        """Modify the region of a mapset

        TODO: Implement region setting

        Args:
            location_name (str): Name of the location
            mapset_name (str): Name of the mapset

        Returns:
            flaks.Response:
            HTTP 200 and JSON document in case of success, HTTP 400 otherwise

        """
        pass

    @swagger.doc({
        'tags': ['Mapset Management'],
        'description': 'Delete an existing mapset. Minimum required user role: admin.',
        'parameters': [
            {
                'name': 'location_name',
                'description': 'The name of the location',
                'required': True,
                'in': 'path',
                'type': 'string'
            },
            {
                'name': 'mapset_name',
                'description': 'The name of the mapset',
                'required': True,
                'in': 'path',
                'type': 'string'
            }
        ],
        'responses': {
            '200': {
                'description': 'Success message for mapset deletion',
                'schema': ProcessingResponseModel
            },
            '400': {
                'description': 'The error message and a detailed error log',
                'schema': ProcessingErrorResponseModel
            }
        }
    })
    def delete(self, location_name, mapset_name):
        """Delete an existing mapset.
        """
        rdc = self.preprocess(has_json=False, has_xml=False,
                              location_name=location_name,
                              mapset_name=mapset_name)

        enqueue_job(self.job_timeout, delete_mapset, rdc)
        http_code, response_model = self.wait_until_finish()
        return make_response(jsonify(response_model), http_code)


class MapsetLockManagementResource(ResourceBase):
    """Lock a mapset
    """
    decorators = [log_api_call, check_user_permissions,
                  very_admin_role, auth.login_required]

    @swagger.doc({
        'tags': ['Mapset Management'],
        'description': 'Get the location/mapset lock status. '
                       'Minimum required user role: admin.',
        'parameters': [
            {
                'name': 'location_name',
                'description': 'The name of the location',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'nc_spm_08'
            },
            {
                'name': 'mapset_name',
                'description': 'The name of the mapset',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'PERMANENT'
            }
        ],
        'responses': {
            '200': {
                'description': 'Get the location/mapset lock status, either '
                               '"True" or "None"',
                'schema': MapsetLockManagementResponseModel
            },
            '400': {
                'description': 'The error message and a detailed error log',
                'schema': ProcessingResponseModel
            }
        }
    })
    def get(self, location_name, mapset_name):
        """Get the location/mapset lock status.
        """
        rdc = self.preprocess(has_json=False, has_xml=False,
                              location_name=location_name,
                              mapset_name=mapset_name)

        enqueue_job(self.job_timeout, get_mapset_lock, rdc)
        http_code, response_model = self.wait_until_finish()
        return make_response(jsonify(response_model), http_code)

    @swagger.doc({
        'tags': ['Mapset Management'],
        'description': 'Create a location/mapset lock. A location/mapset lock can '
                       'be created so that no operation can be performed on it '
                       'until it is unlocked. '
                       'Minimum required user role: admin.',
        'parameters': [
            {
                'name': 'location_name',
                'description': 'The name of the location',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'nc_spm_08'
            },
            {
                'name': 'mapset_name',
                'description': 'The name of the mapset',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'PERMANENT'
            }
        ],
        'responses': {
            '200': {
                'description': 'Success message if the location/mapset was '
                               'locked successfully',
                'schema': ProcessingResponseModel
            },
            '400': {
                'description': 'The error message and a detailed error log',
                'schema': ProcessingResponseModel
            }
        }
    })
    def post(self, location_name, mapset_name):
        """Create a location/mapset lock.
        """
        rdc = self.preprocess(has_json=False, has_xml=False,
                              location_name=location_name,
                              mapset_name=mapset_name)

        enqueue_job(self.job_timeout, lock_mapset, rdc)
        http_code, response_model = self.wait_until_finish()
        return make_response(jsonify(response_model), http_code)

    @swagger.doc({
        'tags': ['Mapset Management'],
        'description': 'Delete a location/mapset lock. A location/mapset lock '
                       'can be deleted so that operation can be performed on '
                       'it until it is locked. '
                       'Minimum required user role: admin.',
        'parameters': [
            {
                'name': 'location_name',
                'description': 'The name of the location',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'nc_spm_08'
            },
            {
                'name': 'mapset_name',
                'description': 'The name of the mapset',
                'required': True,
                'in': 'path',
                'type': 'string',
                'default': 'PERMANENT'
            }
        ],
        'responses': {
            '200': {
                'description': 'Success message if the location/mapset was '
                               'unlocked successfully',
                'schema': ProcessingResponseModel
            },
            '400': {
                'description': 'The error message and a detailed error log',
                'schema': ProcessingResponseModel
            }
        }
    })
    def delete(self, location_name, mapset_name):
        """Delete a location/mapset lock.
        """
        rdc = self.preprocess(has_json=False, has_xml=False,
                              location_name=location_name,
                              mapset_name=mapset_name)

        enqueue_job(self.job_timeout, unlock_mapset, rdc)
        http_code, response_model = self.wait_until_finish()
        return make_response(jsonify(response_model), http_code)
