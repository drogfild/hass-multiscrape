"""Support for RESTful API sensors."""
import logging
from xml.parsers.expat import ExpatError

from bs4 import BeautifulSoup
import requests
from requests import Session
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
import voluptuous as vol
import xmltodict

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_FORCE_UPDATE,
    CONF_HEADERS,
    CONF_METHOD,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PAYLOAD,
    CONF_RESOURCE,
    CONF_RESOURCE_TEMPLATE,
    CONF_TIMEOUT,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_USERNAME,
    CONF_VALUE_TEMPLATE,
    CONF_VERIFY_SSL,
    HTTP_BASIC_AUTHENTICATION,
    HTTP_DIGEST_AUTHENTICATION,
)
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

DEFAULT_METHOD = "GET"
DEFAULT_NAME = "Multiscrape Sensor"
DEFAULT_VERIFY_SSL = True
DEFAULT_FORCE_UPDATE = False
DEFAULT_TIMEOUT = 10
DEFAULT_PARSER = "lxml"

CONF_SELECTORS = "selectors"
CONF_ATTR = "attribute"
CONF_SELECT = "select"
CONF_INDEX = "index"
CONF_PARSER = "parser"

# OT 19.8.2020 Add prelogin parameters
CONF_PRELOGIN = "prelogin"
CONF_PRELOGINPAGE = "preloginpage"
CONF_PRELOGINFORM = "preloginform"
CONF_USERNAMEFIELD = "username_field"
CONF_PASSWORDFIELD = "password_field"
DEFAULT_USERNAMEFIELD = "username"
DEFAULT_PASSWORDFIELD = "password"

METHODS = ["POST", "GET"]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Exclusive(CONF_RESOURCE, CONF_RESOURCE): cv.url,
        vol.Exclusive(CONF_RESOURCE_TEMPLATE, CONF_RESOURCE): cv.template,
        vol.Optional(CONF_AUTHENTICATION): vol.In(
            [HTTP_BASIC_AUTHENTICATION, HTTP_DIGEST_AUTHENTICATION]
        ),
        vol.Optional(CONF_HEADERS): vol.Schema({cv.string: cv.string}),
        vol.Optional(CONF_METHOD, default=DEFAULT_METHOD): vol.In(METHODS),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_PAYLOAD): cv.string,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
        vol.Optional(CONF_FORCE_UPDATE, default=DEFAULT_FORCE_UPDATE): cv.boolean,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Optional(CONF_PARSER, default=DEFAULT_PARSER): cv.string,
        # OT 19.8.2020
        vol.Optional(CONF_PRELOGIN, default={}): vol.Schema({
            vol.Required(CONF_PRELOGINPAGE): cv.url,
            vol.Required(CONF_PRELOGINFORM): cv.string,
            vol.Required(CONF_USERNAME): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
            vol.Optional(CONF_USERNAMEFIELD, default=DEFAULT_USERNAMEFIELD): cv.string,
            vol.Optional(CONF_PASSWORDFIELD, default=DEFAULT_PASSWORDFIELD): cv.string,
        })
    }
)

SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SELECT): cv.string,
        vol.Optional(CONF_ATTR): cv.string,
        vol.Optional(CONF_INDEX, default=0): cv.positive_int,
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_SELECTORS): cv.schema_with_slug_keys(SENSOR_SCHEMA)}
)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the RESTful sensor."""
    name = config.get(CONF_NAME)
    resource = config.get(CONF_RESOURCE)
    resource_template = config.get(CONF_RESOURCE_TEMPLATE)
    method = config.get(CONF_METHOD)
    payload = config.get(CONF_PAYLOAD)
    verify_ssl = config.get(CONF_VERIFY_SSL)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    headers = config.get(CONF_HEADERS)
    unit = config.get(CONF_UNIT_OF_MEASUREMENT)
    value_template = config.get(CONF_VALUE_TEMPLATE)
    selectors = config.get(CONF_SELECTORS)
    # OT 19.8.2020
    prelogin = config.get(CONF_PRELOGIN)
    force_update = config.get(CONF_FORCE_UPDATE)
    timeout = config.get(CONF_TIMEOUT)
    parser = config.get(CONF_PARSER)

    if value_template is not None:
        value_template.hass = hass

    if resource_template is not None:
        resource_template.hass = hass
        resource = resource_template.render()

    if username and password:
        if config.get(CONF_AUTHENTICATION) == HTTP_DIGEST_AUTHENTICATION:
            auth = HTTPDigestAuth(username, password)
        else:
            auth = HTTPBasicAuth(username, password)
    else:
        auth = None
        
    rest = RestData(method, resource, auth, headers, payload, verify_ssl, timeout)
    rest.update()
    
    if rest.data is None:
        raise PlatformNotReady

    # Must update the sensor now (including fetching the rest resource) to
    # ensure it's updating its state.
    add_entities(
        [
            MultiscrapeSensor(
                hass,
                rest,
                name,
                unit,
                value_template,
                selectors,
                force_update,
                resource_template,
                parser,
                prelogin, # OT 19.8.2020
            )
        ],
        True,
    )


class MultiscrapeSensor(Entity):
    """Implementation of a REST sensor."""

    def __init__(
        self,
        hass,
        rest,
        name,
        unit_of_measurement,
        value_template,
        selectors,
        force_update,
        resource_template,
        parser,
        prelogin, # OT 19.8.2020
    ):
        """Initialize the sensor."""
        self._hass = hass
        self.rest = rest
        self._name = name
        self._state = None
        self._unit_of_measurement = unit_of_measurement
        self._value_template = value_template
        self._selectors = selectors
        self._attributes = None
        self._force_update = force_update
        self._resource_template = resource_template
        self._parser = parser
        self._prelogin = prelogin # OT 19.8.2020

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def available(self):
        """Return if the sensor data are available."""
        return self.rest.data is not None

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def force_update(self):
        """Force update."""
        return self._force_update

    def update(self):

        # TODO: Make logic to detect when already logged in. Now if loginform not found assumes we are logged in.
        if self._prelogin:
            _LOGGER.debug("Prelogin started")
            _LOGGER.debug("Preloginpage: %s", self._prelogin[CONF_PRELOGINPAGE])

            previousmethod = self.rest._method

            self.rest.set_url(self._prelogin[CONF_PRELOGINPAGE])
            self.rest.update()

            if self.rest.data is None:
                _LOGGER.error("Unable to retrieve prelogin data for %s", self._name)
                return

            # TODO: value is only used to debug :(
            value = self.rest.data
            #_LOGGER.debug("Prelogin page fetched from resource: %s", value[:35000])
            result = BeautifulSoup(self.rest.data, self._parser)

            # Look for the login form checking these attributes for a match in order: 'name', 'id', 'class', 'action'.
            form = result.find('form', attrs={'name':self._prelogin[CONF_PRELOGINFORM]})
            if form is None:
                form = result.find('form', attrs={'id':self._prelogin[CONF_PRELOGINFORM]})
            if form is None:
                form = result.find('form', attrs={'class':self._prelogin[CONF_PRELOGINFORM]})
            if form is None:
                form = result.find('form', attrs={'action':self._prelogin[CONF_PRELOGINFORM]})

            if form is None:
                _LOGGER.debug("Unable to find form with name %s, assume we are already logged in", self._prelogin[CONF_PRELOGINFORM])
            
            else:

                # Find all fields and extract them to formdata
                # 
                fields = form.findAll('input')
                formdata = dict( (field.get('name'), field.get('value')) for field in fields)

                # Get username and password from config
                formdata[self._prelogin[CONF_USERNAMEFIELD]] = self._prelogin[CONF_USERNAME]
                formdata[self._prelogin[CONF_PASSWORDFIELD]] = self._prelogin[CONF_PASSWORD]

                # Set form data to rest request and post it
                self.rest.set_request_data(formdata)
                # Method is read from the form
                self.rest._method = form['method']
                self.rest.update()

                # TODO: value is only used to debug :(
                value = self.rest.data
                #_LOGGER.debug("Prelogin page fetched after login from resource: %s", value[:2500])


            # Set url back to normal
            #self.rest.set_url(self._resource_template.render())
            # TODO: Set method back to original
            #self.rest._method = self.method
            self.rest._method = previousmethod
            _LOGGER.debug("Prelogin ended")

        else:
            # If not prelogin do normal fetch
            if self._resource_template is not None:
                self.rest.set_url(self._resource_template.render())

            self.rest.update()
        
        if self.rest.data is None:
            _LOGGER.error("Unable to retrieve data for %s", self._name)
            return
        
        value = self.rest.data
        #_LOGGER.debug("Data fetched from resource: %s", value)
        
        if self._selectors:
        
            result = BeautifulSoup(self.rest.data, self._parser)
            result.prettify()
            #_LOGGER.debug("Data parsed by BeautifulSoup: %s", result)

            self._attributes = {}
            if value:
            
                for device, device_config in self._selectors.items():
                    name = device_config.get(CONF_NAME)
                    select = device_config.get(CONF_SELECT)
                    attr = device_config.get(CONF_ATTR)
                    index = device_config.get(CONF_INDEX)
                    value_template = device_config.get(CONF_VALUE_TEMPLATE)
                    unit = device_config.get(CONF_UNIT_OF_MEASUREMENT)
                    
                    try:
                        if attr is not None:
                            value = result.select(select)[index][attr]
                        else:
                            tag = result.select(select)[index]
                            if tag.name in ("style", "script", "template"):
                                value = tag.string
                            else:
                                value = tag.text
                        
                        _LOGGER.debug("Sensor %s selected: %s", name, value)
                    except IndexError as e:
                        _LOGGER.error("Sensor %s was unable to extract data from HTML", name)
                        _LOGGER.debug("Exception: %s", e)
                        continue

                    if value_template is not None:
                    
                        if value_template is not None:
                            value_template.hass = self._hass
                            
                        self._attributes[name] = value_template.render_with_possible_json_value(
                            value, None
                        )
                    else:
                        self._attributes[name] = value

        self._state = "None"
        # OT 21.8.2020
        # TODO: last update would be nice
        #self._attributes['updated'] 

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes


class RestData:
    """Class for handling the data retrieval."""

    def __init__(
        self, method, resource, auth, headers, data, verify_ssl, timeout=DEFAULT_TIMEOUT
    ):
        """Initialize the data object."""
        self._method = method
        self._resource = resource
        self._auth = auth
        self._headers = headers
        self._request_data = data
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._http_session = Session()
        self.data = None
        self.headers = None

    def __del__(self):
        """Destroy the http session on destroy."""
        self._http_session.close()

    def set_url(self, url):
        """Set url."""
        self._resource = url

    def set_request_data(self, request_data):
        """Set request data."""
        self._request_data = request_data

    def update(self):
        """Get the latest data from REST service with provided method."""
        _LOGGER.debug("Updating from %s", self._resource)
        try:
            response = self._http_session.request(
                self._method,
                self._resource,
                headers=self._headers,
                auth=self._auth,
                data=self._request_data,
                timeout=self._timeout,
                verify=self._verify_ssl,
            )
            self.data = response.text
            self.headers = response.headers
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error fetching data: %s failed with %s", self._resource, ex)
            self.data = None
            self.headers = None
