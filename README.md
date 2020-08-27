# Netmetr Python Client

Netmetr is a tool for measuring the actual quality of Internet access services,
such as download and upload speed and latency. It allows users to perform
thorough and detailed testing and get comprehensive information not only about
the status of their particular connection, but also analyze previous measurements
and especially measurements of other participants. All data (excluding personal
data) and source codes are released on the Open Source principle.

## Requirements

- **[rmbt-client](https://github.com/lwimmer/rmbt-client)**: speed measurement 
  client written in C

## Usage

There are 2 types of possible usage:

1. From command line - like an ordinary application. You can either:
    - Install the package and use installed console script `netmetr`
    - Just clone the code and from its root directory run python module using
      `python -m netmetr`

   When using either of the approaches you can use few command line arguments
   that can be displayed using `netmetr -h`

   Example: if you know your `uuid` & use custom control server you can use:
   ```bash
   python3 -m netmetr --uuid <your uuid> --control-server <control server>
   ```

2. Like a library from another python script.
     ```python
     import netmetr
     try:
        results = netmetr.Netmetr().measure()
     except netmetr.NetmetrError as e:
        pass
     ```
     `Netmetr.measure()` returns the overal result of the test in a dictionary
     of the the following form:
     ```python
     {
         'IPv6': {
             'error': 'Not available'
         },
         'IPv4': {
             'download_mbps': 90.69,
             'upload_mbps': 58.08,
             'ping_ms': 4.2
         }
     }
     ```
     Only the protocols which were requested for the measurement are included.

     The exceptions are raised only when general connection problems occurs or in
     case of other general problem. They are **not** risen when either of the
     test fails because there is a good chance that measurement using a different
     protocol can be still carried out.

     To measure only a single protocol you can use methods
     `Netmetr.measure_4()` and `Netmetr.measure_6()`. They return only the
     respective subset of dictionary returned by `Netmetr.measure()` e.g.
     dictionary like this:
     ```python
     {
         'download_mbps': 90.69,
         'upload_mbps': 58.08,
         'ping_ms': 4.2
     }
     ```
     Unlike `Netmetr.measure()`, both `Netmetr.measure_4()` and
     `Netmetr.measure_6()` return only on successfull
     measurement - respective exception is raised otherwise.
