"""
banner — ASCII art + styling for insta_dossier CLI
cyberpunk / hacker aesthetic with color
"""

from .colors import Colors


class Banner:
    """generates and displays the insta_dossier ASCII banner"""

    BANNER_ART = r"""
    ██╗███╗   ██╗███████╗████████╗ █████╗     ██████╗  ██████╗ ███████╗███████╗██╗███████╗██████╗  
    ██║████╗  ██║██╔════╝╚══██╔══╝██╔══██╗    ██╔══██╗██╔═══██╗██╔════╝██╔════╝██║██╔════╝██╔══██╗ 
    ██║██╔██╗ ██║███████╗   ██║   ███████║    ██║  ██║██║   ██║███████╗█████╗  ██║█████╗  ██████╔╝ 
    ██║██║╚██╗██║╚════██║   ██║   ██╔══██║    ██║  ██║██║   ██║╚════██║██╔══╝  ██║██╔══╝  ██╔══██╗ 
    ██║██║ ╚████║███████║   ██║   ██║  ██║    ██████╔╝╚██████╔╝███████║███████╗██║███████╗██║  ██║ 
    ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚══════╝╚═╝╚══════╝╚═╝  ╚═╝ 
                                                                                                        
                        >> instagram osint dossier generator v1.0 <<                                     
                           target → extract → map → reconstruct → export                                
"""

    BANNER_SMALL = r"""
    ██╗███╗   ██╗███████╗████████╗ █████╗ 
    ██║████╗  ██║██╔════╝╚══██╔══╝██╔══██╗
    ██║██╔██╗ ██║███████╗   ██║   ███████║
    ██║██║╚██╗██║╚════██║   ██║   ██╔══██║
    ██║██║ ╚████║███████║   ██║   ██║  ██║
    ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝
                                              
     >> instagram osint dossier v1.0 <<     

"""

    @classmethod
    def display(cls, small: bool = False):
        """print the banner with colors"""
        art = cls.BANNER_SMALL if small else cls.BANNER_ART
        colored_art = Colors.primary(art)
        print(colored_art)

    @classmethod
    def display_simple(cls):
        """minimal banner — just the tagline"""
        print(Colors.primary("  >> insta_dossier v1.0 — instagram osint engine <<"))
        print()

    @classmethod
    def display_target_header(cls, target: str, mode: str = "full", proxies: int = 0):
        """display target info header below banner"""
        print()
        print(f"  {Colors.tag('TARGET')}  {Colors.highlight(f'@{target}')}")
        print(f"  {Colors.tag('MODE')}    {Colors.info(mode)}")
        if proxies:
            print(f"  {Colors.tag('PROXIES')} {Colors.success(str(proxies))} loaded")
        print(f"  {Colors.tag('OUTPUT')}  {Colors.muted('output/dossiers/')}")
        print()

    @classmethod
    def display_divider(cls, text: str = ""):
        """print a styled divider with optional text"""
        width = 60
        if text:
            line = "─" * 4 + f" {text} " + "─" * (width - len(text) - 6)
        else:
            line = "─" * width
        print(f"  {Colors.muted(line)}")
        print()

    @classmethod
    def display_phase_header(cls, phase_num: int, total_phases: int, name: str):
        """print a phase header"""
        print(f"  {Colors.secondary('═' * 60)}")
        print(f"  {Colors.highlight(f'  PHASE {phase_num}/{total_phases} — {name.upper()}')}")
        print(f"  {Colors.secondary('═' * 60)}")
        print()

    @classmethod
    def display_dossier_complete(cls, filepath: str, image_path: str = "", summary: dict = None):
        """display the dossier complete panel"""
        print()
        print(f"  {Colors.success('' + '' * 58 + '')}")
        print(f"  {Colors.success('')}  {Colors.highlight('>> DOSSIER COMPLETE <<')}                            {Colors.success('')}")
        print(f"  {Colors.success('' + '' * 58 + '')}")
        print(f"  {Colors.success('')}                                                    {Colors.success('')}")
        print(f"  {Colors.success('')}  {Colors.tag('📄')} {Colors.info(filepath):<52} {Colors.success('')}")
        if image_path:
            print(f"  {Colors.success('')}  {Colors.tag('🖼')} {Colors.muted(image_path):<52} {Colors.success('')}")
        print(f"  {Colors.success('')}                                                    {Colors.success('')}")

        if summary:
            print(f"  {Colors.success('')}  {Colors.bold('📊 SUMMARY'):<54} {Colors.success('')}")
            for key, value in summary.items():
                line = f"   {key}: {value}"
                print(f"  {Colors.success('')}  {Colors.muted(line[:52]):<52} {Colors.success('')}")

        print(f"  {Colors.success('')}                                                    {Colors.success('')}")
        print(f"  {Colors.success('' + '' * 58 + '')}")
        print()
