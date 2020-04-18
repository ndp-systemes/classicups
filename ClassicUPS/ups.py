import json
import logging
import urllib
import xmltodict
import pprint

from binascii import a2b_base64
from datetime import datetime
from dict2xml import dict2xml

_logger = logging.getLogger(__name__)


class UPSConnection(object):
    test_urls = {
        'track': 'https://wwwcie.ups.com/ups.app/xml/Track',
        'ship_confirm': 'https://wwwcie.ups.com/ups.app/xml/ShipConfirm',
        'ship_accept': 'https://wwwcie.ups.com/ups.app/xml/ShipAccept',
    }
    production_urls = {
        'track': 'https://onlinetools.ups.com/ups.app/xml/Track',
        'ship_confirm': 'https://onlinetools.ups.com/ups.app/xml/ShipConfirm',
        'ship_accept': 'https://onlinetools.ups.com/ups.app/xml/ShipAccept',
    }

    def __init__(self, license_number, user_id, password, shipper_number=None,
                 debug=False):
        self.license_number = license_number
        self.user_id = user_id
        self.password = password
        self.shipper_number = shipper_number
        self.debug = debug

    def _generate_xml(self, url_action, ups_request):
        access_request = {
            'AccessRequest': {
                'AccessLicenseNumber': self.license_number,
                'UserId': self.user_id,
                'Password': self.password,
            }
        }

        xml = u'''
        <?xml version="1.0"?>
        {access_request_xml}

        <?xml version="1.0"?>
        {api_xml}
        '''.format(
            request_type=url_action,
            access_request_xml=dict2xml(access_request),
            api_xml=dict2xml(ups_request),
        )

        return xml

    def _transmit_request(self, url_action, ups_request):
        url = self.production_urls[url_action]
        if self.debug:
            url = self.test_urls[url_action]

        if self.debug:
            _logger.debug("Call service %s on url %s", url_action, url)
            _logger.debug(pprint.pformat(ups_request))
        xml = self._generate_xml(url_action, ups_request)
        resp = urllib.urlopen(url, xml.encode('ascii', 'xmlcharrefreplace')).read()

        resp = UPSResult(resp)
        if self.debug:
            _logger.debug("Result %s on url %s", url_action, url)
            _logger.debug(pprint.pformat(resp.dict_response))
        return resp

    def tracking_info(self, *args, **kwargs):
        return TrackingInfo(self, *args, **kwargs)

    def create_shipment(self, from_addr, to_addr, package_infos, alternate_addr=None, file_format='EPL', reference_numbers=None,
                        shipping_service=None, description='', delivery_confirmation=None):
        return Shipment(ups_conn=self,
                        from_addr=from_addr,
                        to_addr=to_addr,
                        alternate_addr=alternate_addr,
                        package_infos=package_infos,
                        file_format=file_format,
                        reference_numbers=reference_numbers,
                        shipping_service=shipping_service,
                        description=description,
                        delivery_confirmation=delivery_confirmation)


class UPSResult(object):

    def __init__(self, response):
        self.response = response

    @property
    def xml_response(self):
        return self.response

    @property
    def dict_response(self):
        return json.loads(json.dumps(xmltodict.parse(self.xml_response)))


class TrackingInfo(object):

    def __init__(self, ups_conn, tracking_number):
        self.tracking_number = tracking_number

        tracking_request = {
            'TrackRequest': {
                'Request': {
                    'TransactionReference': {
                        'CustomerContext': 'Get tracking status',
                        'XpciVersion': '1.0',
                    },
                    'RequestAction': 'Track',
                    'RequestOption': 'activity',
                },
                'TrackingNumber': tracking_number,
            },
        }

        self.result = ups_conn._transmit_request('track', tracking_request)

    @property
    def shipment_activities(self):
        # Possible Status.StatusType.Code values:
        #   I: In Transit
        #   D: Delivered
        #   X: Exception
        #   P: Pickup
        #   M: Manifest

        shipment_activities = (self.result.dict_response['TrackResponse']['Shipment']['Package']['Activity'])
        if type(shipment_activities) != list:
            shipment_activities = [shipment_activities]

        return shipment_activities

    @property
    def delivered(self):
        delivered = [x for x in self.shipment_activities
                     if x['Status']['StatusType']['Code'] == 'D']
        if delivered:
            return datetime.strptime(delivered[0]['Date'], '%Y%m%d')

    @property
    def in_transit(self):
        in_transit = [x for x in self.shipment_activities
                      if x['Status']['StatusType']['Code'] == 'I']

        return len(in_transit) > 0


class Shipment(object):
    SHIPPING_SERVICES = {
        '1dayair': '01',  # Next Day Air
        '2dayair': '02',  # 2nd Day Air
        'ground': '03',  # Ground
        'express': '07',  # Express
        'worldwide_expedited': '08',  # Expedited
        'standard': '11',  # UPS Standard
        '3_day_select': '12',  # 3 Day Select
        'next_day_air_saver': '13',  # Next Day Air Saver
        'next_day_air_early_am': '14',  # Next Day Air Early AM
        'express_plus': '54',  # Express Plus
        '2nd_day_air_am': '59',  # 2nd Day Air A.M.
        'ups_saver': '65',  # UPS Saver.
        'ups_today_standard': '82',  # UPS Today Standard
        'ups_today_dedicated_courier': '83',  # UPS Today Dedicated Courier
        'ups_today_intercity': '84',  # UPS Today Intercity
        'ups_today_express': '85',  # UPS Today Express
        'ups_today_express_saver': '86',  # UPS Today Express Saver.
    }

    DCIS_TYPES = {
        'no_signature': 1,
        'signature_required': 2,
        'adult_signature_required': 3,
        'usps_delivery_confiratmion': 4,
    }

    def __init__(self,
                 ups_conn,
                 from_addr,
                 to_addr,
                 package_infos,
                 alternate_addr=None,
                 file_format='EPL',
                 reference_numbers=None,
                 shipping_service=None,
                 description='',
                 delivery_confirmation=None):
        """

        :param ups_conn: The UPSConnection instance tu use
        :param ship_desc: the name of the shippement
        :param from_addr: the Shipper Address
        :param to_addr: The delivery Adress
        :param alternate_addr: The Aleternate delivery Adress /ShipmentRequest/Shipment/AlternateDeliveryAddress
        :param package_info: info of the package, dict with dimension, name, weight: only the key weight is mandatory
        :param file_format:
        :param reference_numbers:
        :param shipping_service:
        :param description:
        :param delivery_confirmation:
        """
        shipping_service = shipping_service or {
            'code': 'ground',
            'desc': u"Ground"
        }
        if isinstance(shipping_service, (str, unicode)):
            shipping_service = {'code': shipping_service}

        self.file_format = file_format
        if not isinstance(package_infos, (list, set, tuple)):
            package_infos = [package_infos]
        ups_packages = []
        for package_info in package_infos:
            vals = {
                "Description": package_info.get('desc'),
                'PackagingType': {
                    'Code': package_info.get('type', '02'),
                    # Box (see http://www.ups.com/worldshiphelp/WS11/ENU/AppHelp/Codes/Package_Type_Codes.htm)
                },
                'PackageWeight': {
                    'UnitOfMeasurement': {
                        'Code': package_info.get('weight_unit', 'LBS'),
                    },
                    'Weight': package_info['weight'],
                },
                'PackageServiceOptions': {},
            }
            if package_info.get('fill_dimension', True):
                vals['Dimensions'] = {
                    'UnitOfMeasurement': {
                        'Code': package_info.get('dimensions_unit', 'IN'),
                    },
                    'Length': package_info['length'],
                    'Width': package_info['width'],
                    'Height': package_info['height'],
                }
            ups_packages.append(vals)

        shipping_request = {
            'ShipmentConfirmRequest': {
                'Request': {
                    'TransactionReference': {
                        'CustomerContext': 'get new shipment',
                        'XpciVersion': '1.0001',
                    },
                    'RequestAction': 'ShipConfirm',
                    'RequestOption': 'nonvalidate',  # TODO: what does this mean?
                },
                'Shipment': {
                    'Shipper': {
                        'Name': from_addr['name'],
                        'AttentionName': from_addr.get('attn') if from_addr.get('attn') else from_addr['name'],
                        'PhoneNumber': from_addr['phone'],
                        'ShipperNumber': ups_conn.shipper_number,
                        'EMailAddress': from_addr.get('email', ''),
                        'Address': {
                            'AddressLine1': from_addr['address1'],
                            'City': from_addr['city'],
                            'StateProvinceCode': from_addr['state'],
                            'CountryCode': from_addr['country'],
                            'PostalCode': from_addr['postal_code'],
                        },
                    },
                    'ShipTo': {
                        'CompanyName': to_addr['name'],
                        'AttentionName': to_addr.get('attn') if to_addr.get('attn') else to_addr['name'],
                        'PhoneNumber': to_addr.get('phone'),
                        'EMailAddress': to_addr.get('email', ''),
                        'Address': {
                            'AddressLine1': to_addr['address1'],
                            'City': to_addr['city'],
                            'StateProvinceCode': to_addr['state'],
                            'CountryCode': to_addr['country'],
                            'PostalCode': to_addr['postal_code'],
                            # 'ResidentialAddress': '',  # TODO: omit this if not residential
                        },
                    },
                    'Service': {  # TODO: add new service types
                        'Code': self.SHIPPING_SERVICES.get(shipping_service['code'], shipping_service['code']),
                        'Description': shipping_service.get('desc'),
                    },
                    'PaymentInformation': {  # TODO: Other payment information
                        'Prepaid': {
                            'BillShipper': {
                                'AccountNumber': ups_conn.shipper_number,
                            },
                        },
                    },
                    'Package': ups_packages,
                },
                'LabelSpecification': {  # TODO: support GIF and EPL (and others)
                    'LabelPrintMethod': {
                        'Code': file_format,
                    },
                    'LabelStockSize': {
                        'Width': '6',
                        'Height': '4',
                    },
                    'HTTPUserAgent': 'Mozilla/4.5',
                    'LabelImageFormat': {
                        'Code': 'GIF',
                    },
                },
            },
        }

        if delivery_confirmation:
            shipping_request['ShipmentConfirmRequest']['Shipment']['Package']['PackageServiceOptions']['DeliveryConfirmation'] = {
                    'DCISType': self.DCIS_TYPES[delivery_confirmation]
            }
        if alternate_addr:
            shipping_request['ShipmentConfirmRequest']['Shipment']['AlternateDeliveryAddress'] = {
                'Name': alternate_addr['name'],
                'AttentionName': alternate_addr.get('attn') if alternate_addr.get('attn') else alternate_addr['name'],
                'Address': {
                    'AddressLine1': alternate_addr['address1'],
                    'City': alternate_addr['city'],
                    'StateProvinceCode': alternate_addr['state'],
                    'CountryCode': alternate_addr['country'],
                    'PostalCode': alternate_addr['postal_code'],
                },
            }
        if to_addr.get('location_id'):
            shipping_request['ShipmentConfirmRequest']['Shipment']['ShipTo']['LocationID'] = to_addr.get('location_id')
            shipping_request['ShipmentConfirmRequest']['Shipment']['ShipmentIndicationType'] = {
                'Code': '01'
            }

        if reference_numbers:
            reference_dict = []
            for ref_code, ref_number in enumerate(reference_numbers, 1):
                # allow custom reference codes to be set by passing tuples.
                # according to the docs ("Shipping Package -- WebServices
                # 8/24/2013") ReferenceNumber/Code should hint on the type of
                # the reference number. a list of codes can be found in
                # appendix I (page 503) in the same document.
                try:
                    ref_code, ref_number = ref_number
                except:
                    pass

                reference_dict.append({
                    'Code': ref_code,
                    'Value': ref_number
                })
            # reference_dict[0]['BarCodeIndicator'] = '1'

            if from_addr['country'] == 'US' and to_addr['country'] == 'US':
                shipping_request['ShipmentConfirmRequest']['Shipment']['Package']['ReferenceNumber'] = reference_dict
            else:
                shipping_request['ShipmentConfirmRequest']['Shipment']['Description'] = description
                shipping_request['ShipmentConfirmRequest']['Shipment']['ReferenceNumber'] = reference_dict

        if from_addr.get('address2'):
            shipping_request['ShipmentConfirmRequest']['Shipment']['Shipper']['Address']['AddressLine2'] = from_addr[
                'address2']

        if to_addr.get('company'):
            shipping_request['ShipmentConfirmRequest']['Shipment']['ShipTo']['CompanyName'] = to_addr['company']

        if to_addr.get('address2'):
            shipping_request['ShipmentConfirmRequest']['Shipment']['ShipTo']['Address']['AddressLine2'] = to_addr[
                'address2']

        self.confirm_result = ups_conn._transmit_request('ship_confirm', shipping_request)

        if 'ShipmentDigest' not in self.confirm_result.dict_response['ShipmentConfirmResponse']:
            error_string = self.confirm_result.dict_response['ShipmentConfirmResponse']['Response']['Error'][
                'ErrorDescription']
            raise Exception(error_string)

        confirm_result_digest = self.confirm_result.dict_response['ShipmentConfirmResponse']['ShipmentDigest']
        ship_accept_request = {
            'ShipmentAcceptRequest': {
                'Request': {
                    'TransactionReference': {
                        'CustomerContext': 'shipment accept reference',
                        'XpciVersion': '1.0001',
                    },
                    'RequestAction': 'ShipAccept',
                },
                'ShipmentDigest': confirm_result_digest,
            }
        }

        self.accept_result = ups_conn._transmit_request('ship_accept', ship_accept_request)

    @property
    def cost(self):
        total_cost = self.confirm_result.dict_response['ShipmentConfirmResponse']['ShipmentCharges']['TotalCharges'][
            'MonetaryValue']
        return float(total_cost)

    def package_results(self):
        pkg_results = self.accept_result.dict_response['ShipmentAcceptResponse']['ShipmentResults']['PackageResults']
        if isinstance(pkg_results, dict):
            pkg_results = [pkg_results]
        for pkg_result in pkg_results:
            yield self._convert_pkg_result(pkg_result)

    def _convert_pkg_result(self, ups_package_results):
        """
        Convert a dict ups ShipmentAcceptResponse/ShipmentResults/PackageResults to a more simple python dict

        :param ups_package_results: the  dict from ups PackageResults to convert
        :return: a dict with the key as follow
        'label':  ShipmentAcceptResponse/ShipmentResults/PackageResults/LabelImage/GraphicImage,
        'label_format': ShipmentAcceptResponse/ShipmentResults/PackageResults/LabelImage/Code or self.file_format,
        'tracking_number': ShipmentAcceptResponse/ShipmentResults/PackageResults/TrackingNumber
        """
        return {
            'label': ups_package_results['LabelImage']['GraphicImage'],
            'label_format': ups_package_results['LabelImage']['LabelImageFormat'].get('Code', self.file_format),
            'tracking_number': ups_package_results['TrackingNumber']
        }

    @property
    def tracking_numbers(self):
        return [pkg_res['tracking_number'] for pkg_res in self.package_results()]

    @property
    def tracking_number(self):
        return self.confirm_result.dict_response['ShipmentConfirmResponse']['ShipmentIdentificationNumber']

    def get_label(self):
        label_img = self.accept_result.dict_response['ShipmentAcceptResponse']['ShipmentResults']['PackageResults']
        return a2b_base64(label_img['LabelImage']['GraphicImage'])

    def save_label(self, fd):
        fd.write(self.get_label())
