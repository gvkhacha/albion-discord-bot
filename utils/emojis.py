import configparser
import os

DEFAULT_EMOJIS = {'t1': "\u0031\u20e3", 't2': "\u0032\u20e3", 't3': "\u0033\u20e3", 't4': "\u0034\u20e3", 't5': "\u0035\u20e3", 't6': "\u0036\u20e3", 't7': "\u0037\u20e3",'t8': "\u0038\u20e3"}

def _getConfig() -> 'ConfigParser':
    currentPath = os.path.dirname(os.path.realpath(__file__))
    configs = configparser.ConfigParser()
    configs.read(os.path.dirname(currentPath) + "/config.ini")
    return configs

def getTierEmojis() -> list:
    configs = _getConfig()
    # In case none of them have been defined somehow, use defaults for all
    emojiConfig = configs['Emojis'] if 'Emojis' in configs else DEFAULT_EMOJIS 
    
    emojis = []
    for i in range(8): # tier 1-8
        key = f't{i+1}'
        emojis.append(emojiConfig.get(key, DEFAULT_EMOJIS[key]))

    return emojis


def main():
    emojis = getTierEmojis()
    print(emojis)

if __name__ == "__main__":
    main()