# README

Simple python implementation for displaying satellite positions in **Google Earth** via a **KML** file. It also displays *satellite coverage* and *Line of Sight*.

### Usage

 1. Install [python](https://www.python.org/).
 2. Install [pyephem](http://rhodesmill.org/pyephem/) via **pip** or **easy_install**.
 3. Copy or move or rename **getrack-sample.cfg** as **getrack.cfg** and edit it to your needs.
 4. Execute the script

  ```sh
  $ python getrack.py
  ```
 5. Drag **satellites.kml** into *Google Earth*.

----------


Original readme:
> Copyright (c) 2013 Joseph Armbruster
> 
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
> 
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
> 
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
> 
> This was my quick attempt at making a satellite tracker for Google Earth.
> 
> Getting Started Quickly
> 
> 1. install python
> 2. install pyephem (using pip or easy_install)
> 3. configure getrack.cfg with the following:
>    * spacetrack.org credentials
>    * satellite names of interest
> 4. execute: python getrack.py
> 5. drag-drop satellites.kml into Google Earth
> 6. enjoy !
> 
> The Details
> 
> The getrack.py script performs three main functions:
> 1. generates a satellites.kml file that can be imported into Google Earth 
> 2. manages a simple http server that Google Earth will query for up-2-date orbital data
> 3. performs the ephemeride calculations using pyephem and serves the results up using kml over http
> 
> The satellites.kml file consists of one network link per satellite of interest.  Each network
> link points to a url resource that contains orbital data for the satellite of interest.  The urls
> look like this:
> http://localhost:8080/satellite1
> http://localhost:8080/satellite2
> ...
> 
> where satellite1 may refer to HAMSAT and satellite2 may refer to the ISS.
> This is all transparent to the end-user for the most part, since they will only see "HAMSAT" in the Google Earth temporary places listing.
> For each satellite, orbits are plotted based upon the configured look ahead minutes and tick interval seconds.
> The look ahead minutes defines how leading/trailing the orbit will be in terms of time.
> The tick interval seconds defines how often points will be calculated along the orbit.
> The tracking refresh interval seconds dictates how often Google Earth should ask for new orbital data.
> 
> ###Notes
> - All Keplerian elements are obtained directly from space-track.org, so you will need an account.
> - This script could be easily modified to work with other keplerian element sources (see todos)
> 
> ###Todos
> - add opt-based command line parameters for
>   * caching keps
>   * loading keps from a cache for off-line use
>   * dumping a satellite name list
> - the code needs to be cleaned up
> - calculate and display footprint polygons
> - add some useful metadata to satellite descriptions
> - convert all the swap code to a template engine


----------


> Written with [StackEdit](https://stackedit.io/).