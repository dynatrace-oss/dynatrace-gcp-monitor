""" Vim YouCompleteMe"""
import pathlib

def Settings(**kwargs):
  return {
    "interpreter_path": pathlib.Path(__file__)
      .parent.absolute()
      .joinpath(".venv/bin/python")
  }

