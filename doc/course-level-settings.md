The main settings which are expected to provide access to a WeBWorK server
for problem rendering and grading are expected to be stored in the
"Other Course Settings" JSON dictionary which is available since the
Ironwood release when the ENABLE_OTHER_COURSE_SETTINGS is set to true in the
the cms.env.json file.

The config data is included inside the main JSON object inside a single JSON
object whose key is "webwork_settings".

  * Required to level inner keys:
    * "server_settings" whose value is a object whose keys are the IDs, and each
      value is an object of the settings needed for that server.
    * "course_defaults" whose value is a object whose key-value pairs set default
      values for the current course.

  * Fields in the "server_settings" object:
      * Key = the "ww_server_id" which can be selected to use this group of settings.
      * Value is a object containing at least the following required settings per server:
        * "server_type" either "standalone" or "html2xml"
        * "server_api_url" = the head portion of the URL where the API is.
	  * Examples:
	    * "https://myserver.mydomain.tld/webwork2/html2xml"
	    * "https://myserver.mydomain.tld:3000/render-api"
        * For html2xml servers, there is also
            * "server_static_files_url" which is prepended to URLs in the generated HTML,
              as the man-in-the-middle architecture of loading HTML into the iFrame does
              would not send relative URLS to the WeBWorK server otherwise.
              Example value: "https://myserver.mydomain.tld/webwork2_files".
        * "auth_data" = object of key-value pairs needed for the authentication and
	  secure communucations with the relevant server
          * for "server_type" = "html2xml" this includes:
	    * "ww_course", "ww_username", "ww_password"
            * which are the settings used to authenticate to the daemon course on the server
          * for "server_type" = "standalone" this includes:
            * "aud" (which needs to match `SITE_HOST` set in `render.conf` for the renderer)
            * "problemJWTsecret"
  * Fields in the "course_defaults" object:
    * "default_server" whose value is one of the entries in the prior array. (required)
    * "psvn_shift" (optional) a numeric shift to apply in the current course to PSVN values,
      as for technical reasons for each user they are system-wide values and not course-wide
      values.
    * Additional default settings were under consideration, but have not yet been implemented.

Sample config, which is included inside the main JSON object.

```
{
    "webwork_settings": {
        "server_settings": {
            "LocalStandAloneWW": {
                "server_type": "standalone",
                "server_api_url": "http://standalone.domain.tld:3000/render-api",
                "auth_data": {
                    "aud": "http://standalone.domain.tld:3000",
                    "problemJWTsecret": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
                }
            },
            "RemoteHtml2xml": {
                "server_type": "html2xml",
                "server_api_url": "https://webwork.domain.tld/webwork2/html2xml",
                "server_static_files_url": "https://webwork.domain.tld/webwork2_files",
                "auth_data": {
                    "ww_course": "daemon_course",
                    "ww_username": "the_ww_daemon_course_username",
                    "ww_password": "the_ww_daemon_course_password"
                }
            }
        },
        "course_defaults": {
            "default_server": "LocalStandAloneWW",
            "psvn_shift": 51
        }
    }
}
```

References on the "Other course settings feature":
  - https://www.edunext.co/articles/discover-open-edx-ironwood
  - https://github.com/edx/edx-platform/pull/17699
  - https://openedx.atlassian.net/browse/OSPR-2303
  - https://github.com/edx/edx-documentation/pull/1702

