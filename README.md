### This fork adds possibility to login to html form before scraping. I'm calling it prelogin. See updated example configuration below.
For more info about multipscrape see original author https://github.com/danieldotnl/hass-multiscrape


# HA MultiScrape custom component
This Home Assistant custom component can scrape multiple fields (using CSS selectors) from a single HTTP request (the existing scrape sensor can scrape a single field only).

It is based on both the existing [Rest sensor](https://www.home-assistant.io/integrations/rest/) and the [Scrape sensor](https://www.home-assistant.io/integrations/scrape).
The scraped fields are added as attributes on the sensor and using template sensors, you can see them as separate sensors.
Most properties of the Rest and Scrape sensor apply.


### Example configuration

```yaml

  - platform: multiscrape
    name: home assistant scraper
    resource: https://www.home-assistant.io
    scan_interval: 30
    selectors:
      version:
        name: Current version
        select: '.current-version > h1:nth-child(1)'
        value_template: '{{ (value.split(":")[1]) }}'
      releasedate:
        name: Release date
        select: '.release-date'
    prelogin:
      preloginpage: https://url.of.that.site.com/login.html
      preloginform: 'loginForm'
      username_field: 'username'
      password_field: 'password'
      username: 'yourusername'
      password: 'yourpassword'

```
### Roadmap for this fork
- test test test
