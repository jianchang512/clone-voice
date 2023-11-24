import os
import sys
root_path = os.getcwd()
sys.path.append(root_path)

import os,sys,uvicorn
from testapi import app

@app.get("/")
async def get():
    return "Hello! World!"


if __name__ == "__main__":
    name_app = "testapi"  # Get the name of the script
    log_config={
			"version": 1,
			"disable_existing_loggers": True,
			"handlers": {
				"file_handler": {
					"class": "logging.FileHandler",
					"filename": "logfile.log",
				},
			},
			"root": {
				"handlers": ["file_handler"],
				"level": "INFO",
			},
    }
    uvicorn.run(f'{name_app}:asapp', host="0.0.0.0", port=9988, reload=False,log_config=log_config)
