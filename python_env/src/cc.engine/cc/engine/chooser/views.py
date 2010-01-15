from lxml import etree
from urlparse import urlparse, urljoin
from urllib import quote, unquote_plus, urlencode
from StringIO import StringIO

from webob import Response, exc

from cc.engine import util
from cc.i18npkg import ccorg_i18n_setup
import cc.license
from cc.license.formatters.classes import HTMLFormatter


def _base_context(request):
    context = {
        'request': request,
        'target_lang': (
            request.matchdict.get('target_lang')
            or request.accept_language.best_matches()[0]),
        'active_languages': util.active_languages(),
        'selected_jurisdiction': util.get_selected_jurisdiction(request),
        }
    
    context.update(util.rtl_context_stuff(request))
    return context


def _work_info(request_form):
    """Extract work information from the request and return it as a
    dict."""

    result = {'title' : u'',
              'creator' : u'',
              'copyright_holder' : u'',
              'copyright_year' : u'',
              'description' : u'',
              'format' : u'',
              'type' : u'',
              'work_url' : u'',
              'source_work_url' : u'',
              'source_work_domain' : u'',
              'attribution_name' : u'',
              'attribution_url' : u'',
              'more_permissions_url' : u'',
              }

    # look for keys that match the param names
    for key in request_form:
        if key in result:
            result[key] = request_form[key]

    # look for keys from the license chooser interface

    # work title
    if request_form.has_key('field_worktitle'):
        result['title'] = request_form['field_worktitle']

    # creator
    if request_form.has_key('field_creator'):
        result['creator'] = request_form['field_creator']

    # copyright holder
    if request_form.has_key('field_copyrightholder'):
        result['copyright_holder'] = result['holder'] = \
            request_form['field_copyrightholder']
    if request_form.has_key('copyright_holder'):
        result['holder'] = request_form['copyright_holder']

    # copyright year
    if request_form.has_key('field_year'):
        result['copyright_year'] = result['year'] = request_form['field_year']
    if request_form.has_key('copyright_year'):
        result['year'] = request_form['copyright_year']

    # description
    if request_form.has_key('field_description'):
        result['description'] = request_form['field_description']

    # format
    if request_form.has_key('field_format'):
        result['format'] = result['type'] = request_form['field_format']

    # source url
    if request_form.has_key('field_sourceurl'):
        result['source_work_url'] = result['source-url'] = \
            request_form['field_sourceurl']

        # extract the domain from the URL
        result['source_work_domain'] = urlparse(
            result['source_work_url'])[1]

        if not(result['source_work_domain'].strip()):
            result['source_work_domain'] = result['source_work_url']

    # attribution name
    if request_form.has_key('field_attribute_to_name'):
        result['attribution_name'] = request_form['field_attribute_to_name']

    # attribution URL
    if request_form.has_key('field_attribute_to_url'):
        result['attribution_url'] = request_form['field_attribute_to_url']

    # more permissions URL
    if request_form.has_key('field_morepermissionsurl'):
        result['more_permissions_url'] = request_form['field_morepermissionsurl']

    return result


def _issue_license(request_form):
    """Extract the license engine fields from the request and return a
    License object."""
    jurisdiction = request_form.get('field_jurisdiction')
    version = request_form.get('version', None)

    # Handle public domain class
    if request_form.has_key('pd') or \
            request_form.has_key('publicdomain') or \
            request_form.get('license_code', None) == 'publicdomain':
        return cc.license.by_code('publicdomain')

    # check for license_code
    elif request_form.has_key('license_code'):
        return cc.license.by_code(
            request_form['license_code'],
            jurisdiction=jurisdiction,
            version=version)

    # check for license_url
    elif request_form.has_key('license_url'):
        return cc.license.by_url(request_form['license_url'])

    else:
        ## Construct the license code for a "standard" license
        attribution = request_form.get('field_attribution')
        commercial = request_form.get('field_commercial')
        derivatives = request_form.get('field_derivatives')

        license_code_bits = []
        if not attribution == 'n':
            license_code_bits.append('by')

        if commercial == 'n':
            license_code_bits.append('nc')

        if derivatives == 'n':
            license_code_bits.append('nd')
        elif derivatives == 'sa':
            license_code_bits.append('sa')

        license_code = '-'.join(license_code_bits)
        return cc.license.by_code(
            license_code,
            jurisdiction=jurisdiction,
            version=version)


def _generate_exit_url(url, referrer, license):
    url = unquote_plus(url)

    # test if the exit_url is an absolute uri
    if urlparse(url).scheme not in ['http', 'https']:

        # this will accomodate only for 'valid' relative paths
        # e.g. foo/bar.php or /foo/bar.php?id=1, etc.
        url = urljoin(referrer, url)

    url = url.replace('[license_url]', quote(license.uri))
    url = url.replace('[license_name]', quote(license.title()))
    url = url.replace('[license_button]', quote(license.logo))
    url = url.replace('[deed_url]', quote(license.uri))

    return url


NS_CC = 'http://creativecommons.org/ns#'
NS_DC = 'http://purl.org/dc/elements/1.1/'
NS_DCQ = 'http://purl.org/dc/terms/'
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
LXML_PRE_CC, LXML_PRE_DC, LXML_PRE_DCQ, LXML_PRE_RDF, LXML_PRE_RDFS = map(
    lambda ns: "{%s}" % ns,
    (NS_CC, NS_DC, NS_DCQ, NS_RDF, NS_RDFS))

NSMAP = {
    None: NS_CC,
    "dc": NS_DC,
    "dcq": NS_DCQ,
    "rdf": NS_RDF,
    "rdfs": NS_RDFS}

def _work_rdf(work_info, license):
    rdf_tree = etree.Element(
        LXML_PRE_RDF + 'rdf', nsmap = NSMAP)

    # Work subtree
    work = etree.SubElement(rdf_tree, LXML_PRE_CC + 'Work')
    work.set(LXML_PRE_RDF + 'about', work_info.get('work-url', ''))
    if work_info.get('title'):
        work_title = etree.SubElement(work, LXML_PRE_DC + 'title')
        work_title.text = work_info['title']
    if work_info.get('type'):
        work_type = etree.SubElement(work, LXML_PRE_DC + 'type')
        work_type.set(
            LXML_PRE_RDF + 'resource',
            'http://purl.org/dc/dcmitype/' + work_info['type'])
    if work_info.get('year'):
        work_year = etree.SubElement(work, LXML_PRE_DC + 'date')
        work_year.text = work_info['year']
    if work_info.get('description'):
        work_description = etree.SubElement(work, LXML_PRE_DC + 'description')
        work_description.text = work_info['description']
    if work_info.get('creator'):
        work_creator = etree.SubElement(work, LXML_PRE_DC + 'creator')
        work_creator_agent = etree.SubElement(
            work_creator, LXML_PRE_CC + 'Agent')
        work_creator_agent.text = work_info['creator']
    if work_info.get('holder'):
        work_rights = etree.SubElement(work, LXML_PRE_DC + 'rights')
        work_rights_agent = etree.SubElement(
            work_rights, LXML_PRE_CC + 'Agent')
        work_rights_agent.text = work_info['holder']
    if work_info.get('source-url'):
        work_source = etree.SubElement(work, LXML_PRE_DC + 'source')
        work_source.text = work_info['source']
    work_license = etree.SubElement(work, LXML_PRE_CC + 'license')
    work_license.set(LXML_PRE_RDF + 'resource', license.uri)
    
    license_element = etree.parse(StringIO(license.rdf)).getroot()
    rdf_tree.append(license_element)

    return etree.tostring(rdf_tree)


def chooser_view(request):
    if request.GET.get('partner'):
        template = util.get_zpt_template('chooser_pages/partner/index.pt')
    else:
        template = util.get_zpt_template('chooser_pages/index.pt')

    engine_template = util.get_zpt_template(
        'macros_templates/engine.pt')
    partner_template = util.get_zpt_template(
        'macros_templates/partner.pt')
    metadata_template = util.get_zpt_template(
        'macros_templates/metadata.pt')
    support_template = util.get_zpt_template(
        'macros_templates/support.pt')

    available_jurisdiction_codes = [
        j.code for j in util.get_selector_jurisdictions('standard')]
    
    context = _base_context(request)

    context.update(
        {'engine_template': engine_template,
         'partner_template': partner_template,
         'metadata_template': metadata_template,
         'support_template': support_template,
         'available_jurisdiction_codes': available_jurisdiction_codes,
         'referrer': request.headers.get('REFERER','')})

    return Response(template.pt_render(context))


def choose_results_view(request):
    if request.GET.get('partner'):
        template = util.get_zpt_template('chooser_pages/partner/results.pt')
    else:
        template = util.get_zpt_template('chooser_pages/results.pt')

    engine_template = util.get_zpt_template(
        'macros_templates/engine.pt')

    context = _base_context(request)
    request_form = request.GET or request.POST
    license = _issue_license(request_form)
    work_info = _work_info(request_form)
    license_slim_logo = license.logo_method('80x15')

    html_formatter = HTMLFormatter()
    license_html = html_formatter.format(license, work_info)

    context.update(
        {'engine_template': engine_template,
         'license': license,
         'license_slim_logo': license_slim_logo,
         'license_html': license_html})

    if request.GET.get('partner'):
        context.update(
            {'partner_template': util.get_zpt_template(
                    'macros_templates/partner.pt'),
             'exit_url': _generate_exit_url(
                    request_form.get('exit_url', ''),
                    request_form.get('referrer', ''),
                    license)})

    return Response(template.pt_render(context))


def get_html(request):
    request_form = request.GET or request.POST
    license = _issue_license(request_form)
    work_info = _work_info(request_form)
    html_formatter = HTMLFormatter()
    license_html = html_formatter.format(license, work_info)
    return Response(license_html, content_type='text/html; charset=UTF-8')


def get_rdf(request):
    request_form = request.GET or request.POST
    license = _issue_license(request_form)
    work_info = _work_info(request_form)
    rdf = _work_rdf(work_info, license)

    return Response(rdf, content_type='application/rdf+xml; charset=UTF-8')


def non_web_popup(request):
    request_form = request.GET or request.POST
    license = _issue_license(request_form)
    template = util.get_zpt_template('chooser_pages/nonweb_popup.pt')
    popup_template = util.get_zpt_template('macros_templates/popup.pt')
    is_publicdomain = request_form.get('publicdomain') or request_form.get('pd')
    
    context = _base_context(request)

    context.update(
        {'popup_template': popup_template,
         'license': license,
         'is_publicdomain': is_publicdomain})

    return Response(template.pt_render(context))


def choose_wiki_redirect(request):
    return exc.HTTPTemporaryRedirect(
        location='/choose/results-one?license_code=by-sa')


def work_email_popup(request):
    request_form = request.GET or request.POST
    license = _issue_license(request_form)
    work_info = _work_info(request_form)
    html_formatter = HTMLFormatter()
    license_html = html_formatter.format(license, work_info)

    template = util.get_zpt_template('chooser_pages/htmlpopup.pt')
    popup_template = util.get_zpt_template('macros_templates/popup.pt')
    
    context = _base_context(request)
    context.update(
        {'popup_template': popup_template,
         'license': license,
         'license_html': license_html})

    return Response(template.pt_render(context))


CC_WORK_EMAIL_MESSAGE_TEMPLATE = u"""

Thank you for using a Creative Commons License for your work "%s"

You have selected the %s License. You should include a
reference to this license on the web page that includes the work in question.

Here is the suggested HTML:

%s

Further tips for using the supplied HTML and RDF are here:
http://creativecommons.org/learn/technology/usingmarkup

Thank you!
Creative Commons Support
info@creativecommons.org
"""

def work_email_send(request):
    request_form = request.GET or request.POST
    email_addr = request_form.get('to_email', '')
    work_title = request_form.get('work_title', '')
    license_name = request_form.get('license_name')
    license_html = request_form.get('license_html')

    message_body = CC_WORK_EMAIL_MESSAGE_TEMPLATE % (
        work_title, license_name, license_html)

    util.send_email(
        'info@creativecommons.org', [email_addr],
        'Your Creative Commons License Information',
        message_body)

    template = util.get_zpt_template('chooser_pages/emailhtml.pt')
    popup_template = util.get_zpt_template('macros_templates/popup.pt')

    context = _base_context(request)
    context.update(
        {'request_form': request_form,
         'popup_template': popup_template})

    return Response(template.pt_render(context))


## Special choosers
## ----------------

### FSF

def gpl_chooser(request):
    return util.plain_template_view('chooser_pages/gpl.pt', request)


def lgpl_chooser(request):
    return util.plain_template_view('chooser_pages/lgpl.pt', request)


### Public domain

def publicdomain_landing(request):
    template = util.get_zpt_template(
        'chooser_pages/publicdomain/publicdomain-2.pt')

    engine_template = util.get_zpt_template(
        'macros_templates/engine.pt')
    support_template = util.get_zpt_template(
        'macros_templates/support.pt')

    context = _base_context(request)
    context.update({
            'support_template': support_template,
            'engine_template': engine_template})

    return Response(template.pt_render(context))


def publicdomain_confirm(request):
    template = util.get_zpt_template(
        'chooser_pages/publicdomain/publicdomain-3.pt')

    engine_template = util.get_zpt_template(
        'macros_templates/engine.pt')

    request_form = request.GET or request.POST

    context = _base_context(request)
    context.update({
            'engine_template': engine_template,
            'request_form': request_form})

    return Response(template.pt_render(context))


def publicdomain_result(request):
    request_form = request.GET or request.POST

    # make sure the user selected "confirm"
    if request_form.get('understand', False) != 'confirm':
        return exc.HTTPTemporaryRedirect(
            location='%s?%s' % (
                './publicdomain-3', urlencode(request.GET)))

    work_info = _work_info(request_form)
    html_formatter = HTMLFormatter()
    license_html = html_formatter.format(
        cc.license.by_code('publicdomain'),
        work_info)

    template = util.get_zpt_template(
        'chooser_pages/publicdomain/publicdomain-4.pt')
    engine_template = util.get_zpt_template(
        'macros_templates/engine.pt')

    context = _base_context(request)
    context.update({
            'engine_template': engine_template,
            'request_form': request_form,
            'license_html': license_html})

    return Response(template.pt_render(context))

### CC0
