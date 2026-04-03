# CalSec
A secure calendar tool for tails with hidden service sync

Staying anonymous nowadays becomes more challenging from day to day. One of the most established methods for journalists, activists and people who want to hide in an anonymity set is to use [Tails](https://tails.net). However with tails and the need to undergo surveillance and censorship, you have to face limitations.
Thus including not to trust most third party services without [E2E](https://en.wikipedia.org/wiki/End-to-end_encryption).

When dealing with others you might face the need to share a calendar so everyone stays informed about upcoming events and appointments.
However, using Services without E2E isn't an option. Also trusting companies which claim security and privacy is an advance of trust we might understandably not want to give. So there are two options left:
The most obvious is to host your own hidden service with a calendar tool. Besides the many advantages this could have, we now have the need to secure our Hardware. Also, this isn't an undoable task and there are a lot of cool concepts for hardening and securing local hardware against eavesdropping or actual physical access, this might be overkill for a simple calendar and leaves risks as well.
All your contacts communicating with your local hidden service, leads to your home. No matter the data might be enough protected, you could get into the scope of investigations or attacks. The second option which is used by this too, will be explained in the "Concept" section. 

## Concept
For a shared calendar, we need an accessible server to store and distribute the data. Since we do not want to host such a server ourselves, nor rely on the promises of third-party providers, we instead use a synchronization approach similar to what is used in local password managers.

The calendar data is stored in an encrypted file, which is then synchronized through a third-party service. Other users can download this file and access it locally on their own devices.

While this method does not eliminate all risks, it significantly reduces them by ensuring that the data remains encrypted and under our control.

## Encryption scheme

## Limitations & Risks

## Installation Steps

> [!WARNING]
> For security reasons, you should only install CalSec using the ZIP file from the latest official release on GitHub.
> Be especially cautious when downloading ZIP files from unknown or untrusted sources. Third-party files may have been modified and could contain malicious code.
> Always verify the source before installation to ensure the integrity and safety of your system.


1. Verify the integrity of your local CalSec copy:
    1. Calculate the sha256 hash of the zip: 
        ```bash
        sha256sum calsec.zip
        ```
    2. Compare the output with the hash from the latest [release](https://github.com/inflac/calsec/releases/latest)
    3. If both hashes match, continue.  
          If they do not match, delete your local copy and download a fresh, secure version from the official [release](https://github.com/inflac/calsec/releases/latest)
2. Unzip the file  
3. Open the extracted folder in your file browser  
4. Right-click inside the folder and select **“Open in Terminal”**  
5. Run the following command:
    ```bash
    chmod +x install_calsec.sh
    ```
6. Start the installer: 
    ```bash
    ./install_calsec.sh
    ```
CalSec will be installed automatically. The window will close once the installation is finished.


## Data Locations
CalSec stores its data inside the persistent storage:
```bash
/live/persistence/TailsData_unlocked/
└── calsec/
  ├── calsec          # binary
  ├── icon.png        # icon of the software
  └── calendar.json   # encrypted calendar file
```

The desktop entry for CalSec is stored at:
```bash
/home/amnesia/Persistent/.local/share/applications/
└── calsec.desktop
```

User preferences (e.g. GUI color scheme) are stored at:
```bash
/home/amnesia/Persistent/
└── .calsec/
  └── preferences.json
```