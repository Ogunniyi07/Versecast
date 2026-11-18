import unittest
from scripture_refs import KJV, Session, words_to_digits


class SpokenReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kjv = KJV()

    def labels(self, text):
        return [r.label() for r in self.kjv.find(text)]

    def test_digit_references(self):
        self.assertEqual(self.labels("Turn with me to John 3:16."), ["John 3:16"])
        self.assertEqual(self.labels("Romans 8:28-30"), ["Romans 8:28-30"])
        self.assertEqual(self.labels("Song of Solomon 2:4"), ["Song of Solomon 2:4"])

    def test_spoken_words(self):
        self.assertEqual(self.labels("John chapter three verse sixteen"), ["John 3:16"])
        self.assertEqual(self.labels("First Corinthians chapter thirteen verse four"), ["1 Corinthians 13:4"])
        self.assertEqual(self.labels("Psalm twenty three verse one"), ["Psalms 23:1"])
        self.assertEqual(self.labels("Psalms one hundred nineteen verse one hundred five"), ["Psalms 119:105"])

    def test_ranges(self):
        self.assertEqual(self.labels("1 Corinthians 13 verses 4 to 7"), ["1 Corinthians 13:4-7"])
        self.assertEqual(self.labels("John 3:16 and 17"), ["John 3:16-17"])
        self.assertEqual(self.labels("John 3:16 to 4:2"), ["John 3:16-4:2"])

    def test_single_chapter_books(self):
        self.assertEqual(self.labels("Jude 3"), ["Jude 1:3"])
        self.assertEqual(self.labels("2 John 4"), ["2 John 1:4"])

    def test_verse_text_matches_kjv(self):
        ref = self.kjv.find("John 3:16")[0]
        rows = self.kjv.verse_texts(ref)
        self.assertEqual(rows[0][0:2], (3, 16))
        self.assertTrue(rows[0][2].startswith("For God so loved the world"))

    def test_invalid_references_rejected(self):
        self.assertEqual(self.labels("Genesis 99:1"), [])        # no chapter 99
        self.assertEqual(self.labels("John 3:99"), [])           # no verse 99
        self.assertEqual(self.labels("John 3:16-2"), [])         # reversed range

    def test_chapter_only_shows_whole_chapter(self):
        self.assertEqual(self.labels("That's our story for Matthew 2."), ["Matthew 2:1-23"])
        self.assertEqual(self.labels("Matthew chapter two"), ["Matthew 2:1-23"])
        self.assertEqual(self.labels("Psalm 23 is my favourite"), ["Psalms 23:1-6"])
        self.assertEqual(self.labels("Genesis fifty-one"), [])    # no chapter 51
        # Written as digits, "51" is how Whisper writes a spoken "five one".
        self.assertEqual(self.labels("Genesis 51"), ["Genesis 5:1"])
        self.assertEqual(self.labels("Jude 3"), ["Jude 1:3"])     # one-chapter book: still a verse

    def test_chapter_ranges(self):
        self.assertEqual(self.labels("Genesis 1 to 2"), ["Genesis 1:1-2:25"])
        self.assertEqual(self.labels("Read Romans chapters five to six"), ["Romans 5:1-6:23"])
        self.assertEqual(self.labels("Genesis 1 through 3"), ["Genesis 1:1-3:24"])
        self.assertEqual(self.labels("John 3:16 and 17"), ["John 3:16-17"])   # colon: still verses
        self.assertEqual(self.labels("Jude 3 and 4"), ["Jude 1:3-4"])         # one-chapter book: verses
        self.assertEqual(self.labels("Genesis 2 to 1"), [])                   # backwards
        self.assertEqual(self.labels("Genesis 50 to 51"), [])                 # no chapter 51
        self.assertEqual(self.labels("Acts 2 to 3 weeks ago"), [])            # counting
        self.assertEqual(self.labels("Genesis chapter one and verse two"), ["Genesis 1:2"])
        self.assertEqual(self.labels("Genesis chapter one, verse two"), ["Genesis 1:2"])

    def test_verse_to_end_of_chapter(self):
        self.assertEqual(self.labels("Psalm 119 verse 1 to the end."), ["Psalms 119:1-176"])
        self.assertEqual(self.labels("John 3 from verse sixteen till the end"), ["John 3:16-36"])
        self.assertEqual(self.labels("Romans 8:28 through the end"), ["Romans 8:28-39"])
        self.assertEqual(self.labels("John 3:16 to the end of the service"), ["John 3:16-36"])

    def test_verse_text_has_clean_punctuation(self):
        rows = self.kjv.verse_texts(self.kjv.find("Genesis 4:1")[0])
        self.assertTrue(rows[0][2].endswith("from the LORD."))

    def test_saying_chapter_overrides_counting_guard(self):
        text = ("Because I want you to be able to catch my attention in the book of Genesis "
                "chapter 1 of this book and also in the book of Jeremiah chapter 5 of this book.")
        self.assertEqual(self.labels(text), ["Genesis 1:1-31", "Jeremiah 5:1-31"])
        self.assertEqual(self.labels("Acts chapter 2 weeks ago we read"), ["Acts 2:1-47"])
        self.assertEqual(self.labels("Jude chapter 1"), ["Jude 1:1-25"])
        self.assertEqual(self.labels("Genesis 1 of this book"), ["Genesis 1:1-31"])

    def test_misheard_verse_word(self):
        self.assertEqual(self.labels("John chapter 5 best one"), ["John 5:1"])
        self.assertEqual(self.labels("Genesis chapter 5 based three"), ["Genesis 5:3"])
        self.assertEqual(self.labels("my best 2 friends"), [])
        text = ("I am reading Genesis Chapter 5 based through and I read from the book of "
                "Jud chapter 2 best one and also from the book of John chapter 5 best with Zeng.")
        # "based through" / "best with Zeng" are too garbled; Jude has no chapter 2.
        self.assertEqual(self.labels(text), ["Genesis 5:1-32", "John 5:1-47"])

    def test_and_between_chapters_lists_each_chapter(self):
        # "chapter 1 and 3" means chapters 1 and 3, not 1 through 3.
        self.assertEqual(self.labels("Machu Chapter 1 and 3"), ["Matthew 1:1-25", "Matthew 3:1-17"])
        self.assertEqual(self.labels("Genesis 1 and 2"), ["Genesis 1:1-31", "Genesis 2:1-25"])
        self.assertEqual(self.labels("Psalm 1 and 3 and 5"), ["Psalms 1:1-6", "Psalms 3:1-8", "Psalms 5:1-12"])
        self.assertEqual(self.labels("Genesis 50 and 51"), ["Genesis 50:1-26"])   # 51 doesn't exist
        self.assertEqual(self.labels("John 3:16 and 17"), ["John 3:16-17"])       # verses: still a range
        self.assertEqual(self.labels("Jude 3 and 4"), ["Jude 1:3-4"])
        self.assertEqual(self.labels("pick numbers 1 and 2 and 3 and 4"), [])     # long list: counting

    def test_comma_after_book_name(self):
        text = ("I mentioned the book of Chapter 1, both Daniel, Chapter 2, verse 5. "
                "Both I also mentioned Machu Chapter 1 and 3.")
        self.assertEqual(self.labels(text), ["Daniel 2:5", "Matthew 1:1-25", "Matthew 3:1-17"])
        self.assertEqual(self.labels("Thank you John, 3 more things"), [])  # no "chapter": not a reference

    def test_chapter_only_ignores_counting(self):
        self.assertEqual(self.labels("we met on Acts 2 weeks ago"), [])
        self.assertEqual(self.labels("Job 2 years ago"), [])
        self.assertEqual(self.labels("pick numbers 1 through 10"), [])
        self.assertEqual(self.labels("Mark 3 or 4 of them"), [])

    def test_comma_or_space_between_chapter_and_verse(self):
        # How Whisper often writes a spoken "John three sixteen".
        self.assertEqual(self.labels("And that's also for John 3, 16."), ["John 3:16"])
        self.assertEqual(self.labels("John 3 16"), ["John 3:16"])
        self.assertEqual(self.labels("John three sixteen"), ["John 3:16"])
        self.assertEqual(self.labels("Romans 8, 28 through 30"), ["Romans 8:28-30"])
        self.assertEqual(self.labels("First Corinthians 13, 4"), ["1 Corinthians 13:4"])

    def test_number_lists_are_not_references(self):
        self.assertEqual(self.labels("write the numbers 1, 2, 3 on the board"), [])
        self.assertEqual(self.labels("Numbers 1 2 3 4"), [])
        self.assertEqual(self.labels("John 3, 99"), [])   # still checked against the KJV

    def test_ordinary_speech_is_not_a_reference(self):
        self.assertEqual(self.labels("He said the spirit of the Lord"), [])
        self.assertEqual(self.labels("Mark 5 people came in"), [])
        self.assertEqual(self.labels("for one of the people in the room"), [])

    def test_multiple_references_in_one_chunk(self):
        self.assertEqual(
            self.labels("Read John 3:16 and then Romans 5:8"),
            ["John 3:16", "Romans 5:8"],
        )

    def test_repeated_reference_counts_as_latest(self):
        self.assertEqual(
            self.labels("John 3:16, then Romans 5:8, and back to John 3:16"),
            ["Romans 5:8", "John 3:16"],
        )

    def test_whisper_number_styles(self):
        self.assertEqual(self.labels("Ephesians 6-10 to the end of the chapter."), ["Ephesians 6:10-24"])
        self.assertEqual(self.labels("Revelations 21-4."), ["Revelation 21:4"])
        self.assertEqual(self.labels("Esther 8-9."), ["Esther 8:9"])
        self.assertEqual(self.labels("Amos 33."), ["Amos 3:3"])
        self.assertEqual(self.labels("Acts 18."), ["Acts 18:1-28"])          # chapter 18 exists: keep
        self.assertEqual(self.labels("Rev. 2213."), ["Revelation 22:13"])
        self.assertEqual(self.labels("John 340."), [])                        # 3:40 doesn't exist
        self.assertEqual(self.labels("Romans eight twenty eight and onward"), ["Romans 8:28-39"])
        self.assertEqual(self.labels("John 3, Col. 16."), ["John 3:16"])
        self.assertEqual(self.labels("Romans 10, 9, and 10."), ["Romans 10:9-10"])
        self.assertEqual(self.labels("Matthew 5 verse 3. Then verse 8."), ["Matthew 5:3", "Matthew 5:8"])
        self.assertEqual(self.labels("John 3:16-18"), ["John 3:16-18"])       # verse range unchanged
        self.assertEqual(self.labels("We have 33 members"), [])
        self.assertEqual(self.labels("Psalm 23 verse 1-6."), ["Psalms 23:1-6"])
        self.assertEqual(self.labels("Matthew 5 verses 3-12."), ["Matthew 5:3-12"])
        self.assertEqual(self.labels("Genesis chapters 1-3."), ["Genesis 1:1-3:24"])
        self.assertEqual(self.labels("The Bible says in John 14, 6, I am the way."), ["John 14:6"])

    def test_number_words(self):
        self.assertEqual(words_to_digits("one hundred and nineteen"), "119")
        self.assertEqual(words_to_digits("twenty-three"), "23")
        self.assertEqual(words_to_digits("three sixteen"), "3 16")
        self.assertEqual(words_to_digits("eight twenty eight"), "8 28")
        self.assertEqual(words_to_digits("one hundred nineteen one hundred five"), "119 105")



class QuotationTests(unittest.TestCase):
    """A verse quoted without its reference."""

    @classmethod
    def setUpClass(cls):
        cls.kjv = KJV()

    def quote(self, text):
        ref = self.kjv.find_quote(text)
        return ref.label() if ref else None

    def test_kjv_wording(self):
        self.assertEqual(self.quote("For God so loved the world, that he gave his only begotten Son"), "John 3:16")
        self.assertEqual(self.quote("I can do all things through Christ which strengtheneth me"), "Philippians 4:13")
        self.assertEqual(self.quote("Trust in the LORD with all thine heart; and lean not unto thine own understanding"), "Proverbs 3:5")

    def test_short_famous_lines(self):
        self.assertEqual(self.quote("for God so loved the world"), "John 3:16")
        self.assertEqual(self.quote("the Lord is my shepherd"), "Psalms 23:1")
        self.assertEqual(self.quote("Jesus wept"), "John 11:35")
        self.assertEqual(self.quote("pray without ceasing"), "1 Thessalonians 5:17")

    def test_modern_wording(self):
        self.assertEqual(self.quote("I can do all things through Christ who strengthens me"), "Philippians 4:13")
        self.assertEqual(self.quote("your word is a lamp to my feet and a light to my path"), "Psalms 119:105")
        self.assertEqual(self.quote("this is the day that the Lord has made"), "Psalms 118:24")
        self.assertEqual(self.quote("no weapon formed against me shall prosper"), "Isaiah 54:17")

    def test_quote_inside_a_sentence(self):
        self.assertEqual(self.quote("so the preacher said for God so loved the world that he gave "
                                    "his only begotten son and that is the gospel"), "John 3:16")

    def test_quote_across_verses(self):
        self.assertEqual(self.quote("the Lord is my shepherd I shall not want he maketh me to lie "
                                    "down in green pastures"), "Psalms 23:1-2")

    def test_ordinary_speech_is_not_a_quote(self):
        for text in [
            "we have three services on sunday and everybody is welcome to come",
            "god loves you and he wants the best for your life this morning",
            "good morning church it is good to be in the house of the lord today",
            "lift up your hands and give the lord a praise",
            "the lord has been faithful to us throughout this year",
            "in the name of jesus we pray amen",
        ]:
            self.assertIsNone(self.quote(text), text)

    def test_stock_phrases_in_many_verses_are_ignored(self):
        self.assertIsNone(self.quote("and the Lord spake unto Moses saying"))
        self.assertIsNone(self.quote("verily verily I say unto you"))
        self.assertIsNone(self.quote("the earth is the Lord's and the fulness thereof"))  # Ps 24:1 = 1 Cor 10:26

    def test_session_uses_quotes_but_keeps_the_passage_on_screen(self):
        s = Session(self.kjv)
        self.assertEqual([r.label() for r in s.hear("for God so loved the world")], ["John 3:16"])
        s = Session(self.kjv)
        s.hear("John 3:16 to 18")
        # Reading the displayed passage aloud doesn't replace it with one verse.
        self.assertEqual(s.hear("for God sent not his Son into the world to condemn the world"), [])
        self.assertEqual(s.last.label(), "John 3:16-18")
        # A spoken reference still wins over a quote.
        self.assertEqual([r.label() for r in s.hear("Romans 8:28, for God so loved the world")], ["Romans 8:28"])


class LiveSermonTests(unittest.TestCase):
    """What the preacher reads aloud corrects a missed or misheard reference."""

    @classmethod
    def setUpClass(cls):
        cls.kjv = KJV()

    def screen(self, *said, start=None):
        s = Session(self.kjv)
        if start:
            s.last = self.kjv.find(start)[-1]
        for text in said:
            s.hear(text)
        return s.last.label() if s.last else None

    def test_reading_overrides_a_misheard_reference(self):
        self.assertEqual(self.screen("Genesis eleven in the beginning God created the heaven and the earth"), "Genesis 1:1")
        self.assertEqual(self.screen("Genesis eleven", "in the beginning God created the heaven and the earth"), "Genesis 1:1")
        self.assertEqual(self.screen("Jeremiah one one", "in the beginning God created the heaven and the earth"), "Genesis 1:1")

    def test_misheard_reference_stays_in_the_list(self):
        refs = Session(self.kjv).hear("Genesis eleven in the beginning God created the heaven and the earth")
        self.assertEqual([r.label() for r in refs], ["Genesis 11:1-32", "Genesis 1:1"])

    def test_missed_reference_and_speech_slips(self):
        self.assertEqual(self.screen("in the beginning God create a heaven and earth"), "Genesis 1:1")

    def test_screen_follows_the_reading(self):
        # Alone, this is also Jeremiah 4:23; with Genesis 1:1 on screen it is Genesis 1:2.
        self.assertIsNone(self.screen("and the earth was without form and void"))
        self.assertEqual(self.screen("Genesis 1:1", "and the earth was without form and void"), "Genesis 1:2")

    def test_reading_what_is_on_screen_changes_nothing(self):
        self.assertEqual(self.screen("Genesis 1:1", "in the beginning God created the heaven and the earth"), "Genesis 1:1")
        self.assertEqual(self.screen("Genesis 1", "and the earth was without form and void"), "Genesis 1:1-31")

    def test_repeated_phrase_in_the_chapter_is_ignored(self):
        self.assertEqual(self.screen("Genesis 1:3", "and God saw that it was good"), "Genesis 1:3")


class PausedQuoteTests(unittest.TestCase):
    """A quote said in pieces, with pauses between them, still adds up."""

    @classmethod
    def setUpClass(cls):
        cls.kjv = KJV()

    def shown(self, *said, gap=4):
        s = Session(self.kjv)
        return [[r.label() for r in s.hear(text, now=100 + i * gap)] for i, text in enumerate(said)]

    def test_pieces_add_up(self):
        self.assertEqual(self.shown("eyes have not seen", "nor ears heard"), [[], ["1 Corinthians 2:9"]])
        self.assertEqual(self.shown("eyes have not seen", "neither has ears heard",
                                    "neither has it entered into the heart of man")[-1], ["1 Corinthians 2:9"])

    def test_a_long_pause_starts_afresh(self):
        self.assertEqual(self.shown("eyes have not seen", "nor ears heard", gap=20), [[], []])

    def test_finished_quote_is_not_shown_twice(self):
        self.assertEqual(self.shown("for God so loved the world", "that he gave his only begotten son"),
                         [["John 3:16"], []])

    def test_ordinary_sentences_stay_quiet(self):
        self.assertEqual(self.shown("we thank God for this service", "and we are all here today",
                                    "so please greet your neighbour"), [[], [], []])


class BibleStoryTests(unittest.TestCase):
    """A story mentioned by name opens where it starts in the Bible."""

    @classmethod
    def setUpClass(cls):
        cls.kjv = KJV()

    def labels(self, text):
        return [r.label() for r in self.kjv.find(text)]

    def test_stories_by_name(self):
        for text, want in [
            ("David and Goliath", "1 Samuel 17:1-58"),
            ("Jonah and the whale", "Jonah 1:1-17"),
            ("Noah's ark", "Genesis 6:1-22"),
            ("the prodigal son", "Luke 15:11-32"),
            ("the walls of Jericho", "Joshua 6:1-27"),
        ]:
            self.assertEqual(self.labels(text), [want], text)

    def test_story_of_a_person(self):
        self.assertEqual(self.labels("The story of Daniel in the Bible"), ["Daniel 1:1-21"])
        self.assertEqual(self.labels("Joseph's story"), ["Genesis 37:1-36"])
        self.assertEqual(self.labels("joseph story"), ["Genesis 37:1-36"])

    def test_specific_episode_wins_over_the_person(self):
        self.assertEqual(self.labels("the story of Daniel in the lions den"), ["Daniel 6:1-28"])

    def test_misheard_names(self):
        self.assertEqual(self.labels("Shadrach, Meshach and Abednego"), ["Daniel 3:1-30"])
        self.assertEqual(self.labels("Shedrach, mechash and abenego story"), ["Daniel 3:1-30"])

    def test_spoken_numbers_win(self):
        self.assertEqual(self.labels("the story of Daniel chapter 3"), ["Daniel 3:1-30"])

    def test_names_alone_are_not_stories(self):
        self.assertEqual(self.labels("my friend Daniel is here today"), [])
        self.assertEqual(self.labels("Joseph will lead the prayer"), [])



class RetellingTests(unittest.TestCase):
    """A story told in the preacher's own words, without naming it."""

    @classmethod
    def setUpClass(cls):
        cls.kjv = KJV()

    def story(self, text):
        r = self.kjv.find_story(text)
        return f"{r.book} {r.chapter}" if r else None

    def test_retellings_with_names(self):
        self.assertEqual(self.story("king Darius could not sleep all night because Daniel was in the den of lions "
                                    "and in the morning he ran to the den and the lions had not touched him"), "Daniel 6")
        self.assertEqual(self.story("the giant from Gath came out every day and defied the armies of Israel until a "
                                    "shepherd boy picked five smooth stones and put one in his sling"), "1 Samuel 17")
        self.assertEqual(self.story("God told him to go to Nineveh but he ran the other way and got on a ship to "
                                    "Tarshish and there was a great storm"), "Jonah 1")

    def test_retellings_without_names(self):
        self.assertEqual(self.story("the younger son asked his father for his share of the inheritance and wasted it "
                                    "all in riotous living until he was feeding swine and wished he could eat the husks"), "Luke 15")
        self.assertEqual(self.story("God told him to build an ark of gopher wood and bring the animals two by two "
                                    "because he would send a flood upon the earth"), "Genesis 6")

    def test_story_told_twice_shows_the_original(self):
        self.assertEqual(self.story("Saul was on his way to Damascus to arrest the believers when a light from heaven "
                                    "shone around him and he heard a voice saying why do you persecute me"), "Acts 9")

    def test_sermon_imagery_is_not_a_retelling(self):
        for text in [
            "when the storm is raging and the waves are high and your boat is filling with water remember that "
            "He is in the boat with you He can speak peace to your storm",
            "watch the Lord multiply it like the loaves and the fish The wilderness is not your final destination "
            "God fed his people with manna in the wilderness and water from the rock",
            "Plead the blood over your family and your business this week Do not be like the foolish man who "
            "built his house on the sand Build on the rock",
            "every giant in your life must fall in the name of Jesus you do not need armour you need the anointing",
        ]:
            self.assertIsNone(self.story(text), text)

    def test_retelling_across_sentences(self):
        s = Session(self.kjv)
        self.assertEqual(s.hear("king Darius was so worried he fasted and nobody could comfort him"), [])
        refs = s.hear("because Daniel was in the den of lions and the king ran to the den in the morning")
        self.assertEqual([r.label() for r in refs], ["Daniel 6:1-28"])

    def test_retelling_of_the_chapter_on_screen_changes_nothing(self):
        s = Session(self.kjv)
        s.hear("Daniel 6:16")
        s.hear("king Darius was so worried he fasted and nobody could comfort him")
        self.assertEqual(s.hear("because Daniel was in the den of lions and the king ran to the den"), [])
        self.assertEqual(s.last.label(), "Daniel 6:16")


if __name__ == "__main__":
    unittest.main()
