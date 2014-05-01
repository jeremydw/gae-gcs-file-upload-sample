# Google App Engine <-> Google Cloud Storage sample application

Demonstrates one way to write an App Engine application that stores
user-uploaded avatars and serves them directly to users from Google
Cloud Storage.

Serving directly from GCS is cheaper, faster, and better.

## Request architecture overview

     +------+       +-----+       +-----+  
     |      | +---> | GAE | +---> |     |  
     | User |       +-----+       | GCS |  
     |      |                     |     |  
     +------+ <-----------------+ +-----+  
