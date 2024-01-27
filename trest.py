from bot.horde import HordeMultiGen
import time


if __name__ == "__main__":
    # simple_generate_example()

    htest = HordeMultiGen([{'prompt': 'a slutty soccer mom, having vigorous sex, naked, cowgirl, orgasm###', 'nsfw': True, 'censor_nsfw': False, 'r2': True, 'shared': True, 'trusted_workers': True, 'models': ['Fustercluck'], 'params': {'n': 1, 'karras': True, 'width': 832, 'height': 1216, 'sampler_name': 'k_dpmpp_sde', 'steps': 10, 'cfg_scale': 2.5, 'hires_fix': False, 'loras': [{'name': '247778', 'model': 1, 'is_version': True}]}}, {'prompt': 'a slutty soccer mom, having vigorous sex, naked, cowgirl, orgasm###', 'nsfw': True, 'censor_nsfw': False, 'r2': True, 'shared': True, 'trusted_workers': True, 'models': ['Fustercluck'], 'params': {'n': 1, 'karras': True, 'width': 832, 'height': 1216, 'sampler_name': 'k_dpmpp_sde', 'steps': 10, 'cfg_scale': 2.5, 'hires_fix': False, 'loras': [{'name': '247778', 'model': 1, 'is_version': True}]}}, {'prompt': 'a slutty soccer mom###', 'nsfw': False, 'censor_nsfw': True, 'r2': True, 'shared': True, 'trusted_workers': True, 'models': ['Fustercluck'], 'params': {'n': 1, 'karras': True, 'width': 832, 'height': 1216, 'sampler_name': 'k_dpmpp_sde', 'steps': 10, 'cfg_scale': 2.5, 'hires_fix': False, 'loras': [{'name': '247778', 'model': 1, 'is_version': True}]}}, {'prompt': 'a slutty soccer mom###', 'nsfw': False, 'censor_nsfw': True, 'r2': True, 'shared': True, 'trusted_workers': True, 'models': ['Fustercluck'], 'params': {'n': 1, 'karras': True, 'width': 832, 'height': 1216, 'sampler_name': 'k_dpmpp_sde', 'steps': 10, 'cfg_scale': 2.5, 'hires_fix': False, 'loras': [{'name': '247778', 'model': 1, 'is_version': True}]}}],'aaaaaaa')
    while not htest.all_gens_done():
        time.sleep(1)
